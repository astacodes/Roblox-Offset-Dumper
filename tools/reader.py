import re
import ctypes, win32job # type: ignore
windll = ctypes.windll

kernel32 = windll.kernel32
ntdll = windll.ntdll

ALLOWED_PROTECTIONS = [
    0x02, # PAGE_READONLY
    0x04, # PAGE_READWRITE
    0x20, # PAGE_EXECUTE_READONLY
    0x40 # PAGE_EXECUTE_READWRITE
]

PROTECTIONS = {
    "READ_ONLY": 0x02,
    "READ_WRITE": 0x04,
    "EXEC_READ_ONLY": 0x20,
    "EXEC_READ_WRITE": 0x40,
}

JobObjectFreezeInformation = 18

class MEMORY_BASIC_INFORMATION32(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_ulong),
        ("AllocationBase", ctypes.c_ulong),
        ("AllocationProtect", ctypes.c_ulong),
        ("RegionSize", ctypes.c_ulong),
        ("State", ctypes.c_ulong),
        ("Protect", ctypes.c_ulong),
        ("Type", ctypes.c_ulong)
    ]

class MEMORY_BASIC_INFORMATION64(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_ulonglong),
        ("AllocationBase", ctypes.c_ulonglong),
        ("AllocationProtect", ctypes.c_ulong),
        ("RegionSize", ctypes.c_ulonglong),
        ("State", ctypes.c_ulong),
        ("Protect", ctypes.c_ulong),
        ("Type", ctypes.c_ulong),
    ]


class JOBOBJECT_WAKE_FILTER(ctypes.Structure):
    _fields_ = [
        ("HighEdgeFilter", ctypes.c_ulong),
        ("LowEdgeFilter", ctypes.c_ulong)
    ]

class JOBOBJECT_FREEZE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("Flags", ctypes.c_ulong),
        ("Freeze", ctypes.c_bool),
        ("Swap", ctypes.c_bool),
        ("Reserved0", ctypes.c_char * 2),
        ("WakeFilter", JOBOBJECT_WAKE_FILTER)
    ]


ptr_size = ctypes.sizeof(ctypes.c_void_p)
if ptr_size == 8:
    MEMORY_BASIC_INFORMATION = MEMORY_BASIC_INFORMATION64
elif ptr_size == 4:
    MEMORY_BASIC_INFORMATION = MEMORY_BASIC_INFORMATION32

kernel32.VirtualQueryEx.argtypes = [
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.POINTER(MEMORY_BASIC_INFORMATION),
    ctypes.c_ulong
]

kernel32.VirtualQueryEx.restype = ctypes.c_ulong
kernel32.VirtualAllocEx.restype = ctypes.c_void_p

class Memopy:
    ctypes = ctypes
    process_handle = -1

    def __init__(self, process: int):
        self.process_handle = kernel32.OpenProcess(0x1F0FFF, False, process)
        self.hJob = kernel32.CreateJobObjectA(None,None)

    def update_pid(self, pid: int):
        self.process_handle = kernel32.OpenProcess(0x1F0FFF, False, pid)

    def suspend(self):
        job_info = JOBOBJECT_FREEZE_INFORMATION()
        job_info.Flags = 1
        job_info.Freeze = True


        kernel32.SetInformationJobObject(self.hJob, JobObjectFreezeInformation, ctypes.byref(job_info), ctypes.sizeof(job_info))
        kernel32.AssignProcessToJobObject(self.hJob, self.process_handle)

    def resume(self):
        job_info = JOBOBJECT_FREEZE_INFORMATION()
        job_info.Flags = 1 
        job_info.Freeze = False

        ctypes.windll.kernel32.SetInformationJobObject(self.hJob, JobObjectFreezeInformation, ctypes.byref(job_info), ctypes.sizeof(job_info))
        win32job.AssignProcessToJobObject(self.hJob, self.process_handle)


    def cleanup(self):
        kernel32.CloseHandle(self.hJob)
        kernel32.CloseHandle(self.process_handle)

    def virtual_query(self, address: int):
        memory_basic_info = MEMORY_BASIC_INFORMATION()

        kernel32.VirtualQueryEx(
            self.process_handle,
            ctypes.c_void_p(address),
            ctypes.byref(memory_basic_info),
            ctypes.sizeof(memory_basic_info)
        )

        return memory_basic_info

    def pattern_scan(self, pattern: bytes, single=True):
        region = 0
        found = [] if not single else None
        while region < 0x7FFFFFFF0000:
            mbi = self.virtual_query(region)

            if mbi.State != 0x1000 or mbi.Protect not in ALLOWED_PROTECTIONS:
                region += mbi.RegionSize
                continue

            current_bytes = self.read_bytes(region, mbi.RegionSize)

            if single:
                match = re.search(pattern, current_bytes, re.DOTALL)

                if match:
                    found = region + match.span()[0]
                    break
            else:
                for match in re.finditer(pattern, current_bytes, re.DOTALL):
                    found_address = region + match.span()[0]
                    found.append(found_address)

            region += mbi.RegionSize

        return found

    # memory functions

    def virtual_protect(self, address: int, size: int, protect_val: int):
        old_prot_val = ctypes.c_ulong()
        kernel32.VirtualProtectEx(
            self.process_handle,
            ctypes.c_void_p(address),
            size,
            ctypes.c_ulong(protect_val),
            ctypes.byref(old_prot_val)
        )
        return old_prot_val.value

    def unlock_memory(self, address: int, size: int):
        return ntdll.NtUnlockVirtualMemory(
            self.process_handle,
            ctypes.c_void_p(address),
            size,
            0x01
        )

    def allocate_memory(self, size: int, address: int = None) -> int:
        return kernel32.VirtualAllocEx(
            self.process_handle,
            (ctypes.c_void_p(address) if address else None),
            size,
            0x1000 | 0x2000, # MEM_COMMIT | MEM_RESERVE
            PROTECTIONS["READ_WRITE"]
        )

    def free_memory(self, address: int, size: int):
        return kernel32.VirtualFreeEx(
            self.process_handle,
            ctypes.c_void_p(address),
            size,
            0x4000
        )

    def read_memory(self, buffer, address: int):
        size = ctypes.sizeof(buffer)
        kernel32.ReadProcessMemory(
            self.process_handle,
            ctypes.c_void_p(address),
            ctypes.byref(buffer),
            size,
            None
        )
        self.unlock_memory(address, size)

    def write_memory(self, buffer, address: int) -> None:
        size = ctypes.sizeof(buffer)
        old_prot = self.virtual_protect(address, size, PROTECTIONS["READ_WRITE"])
        kernel32.WriteProcessMemory(
            self.process_handle,
            ctypes.c_void_p(address),
            ctypes.pointer(buffer),
            size,
            None
        )
        self.virtual_protect(address, size, old_prot)

    def read_byte(self, address: int) -> bytes:
        buffer = ctypes.c_char()
        self.read_memory(buffer, address)
        return buffer.value[0]

    def read_bytes(self, address: int, length=4096) -> bytes:
        buffer = (length * ctypes.c_char)()
        self.read_memory(buffer, address)
        return buffer.raw

    def read_string(self, address: int, length=100) -> str:
        return self.read_bytes(address, length).split(b"\x00")[0].decode(errors="ignore")

    def read_double(self, address: int) -> float:
        buffer = ctypes.c_double()
        self.read_memory(buffer, address)
        return buffer.value

    def read_float(self, address: int) -> float:
        buffer = ctypes.c_float()
        self.read_memory(buffer, address)
        return buffer.value

    def read_long(self, address: int) -> int:
        buffer = ctypes.c_long()
        self.read_memory(buffer, address)
        return buffer.value

    def read_longlong(self, address: int) -> int:
        buffer = ctypes.c_longlong()
        self.read_memory(buffer, address)
        return buffer.value

    def write_byte(self, address: int, value):
        buffer = ctypes.c_char(value)
        self.write_memory(buffer, address)

    def write_bytes(self, address: int, value: bytes):
        buffer = (len(value) * ctypes.c_char)(*value)
        self.write_memory(buffer, address)

    def write_string(self, address: int, value: str):
        new_string = value.encode(errors="ignore") + b"\x00"
        self.write_bytes(address, new_string)

    def write_double(self, address: int, value: float):
        buffer = ctypes.c_double(value)
        self.write_memory(buffer, address)

    def write_float(self, address: int, value: float):
        buffer = ctypes.c_float(value)
        self.write_memory(buffer, address)

    def write_long(self, address: int, value: int):
        buffer = ctypes.c_long(value)
        self.write_memory(buffer, address)

    def write_longlong(self, address: int, value: int):
        buffer = ctypes.c_longlong(value)
        self.write_memory(buffer, address)
