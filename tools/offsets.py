class Offsets:
    DataModelHolder = 0x118
    DataModel = 0x198
    module_iscore = 0x198
    Name = 0x48
    Children = 0x50
    Parent = 0x60
    ClassDescriptor = 0x18
    ValueBase = 0xC0
    ModuleFlags = 0x192
    BytecodeSize = 0xA8
    Bytecode = {
        "LocalScript": 0x1B8,
        "ModuleScript": 0x150
    }
    
Capabilities = {
    0x0: "None",
    0x1: "Plugin",
    0x2: "LocalUser",
    0x4: "WritePlayer",
    0x8: "RobloxScriptSecurity",
    0x10: "RobloxEngine",
    0x20: "NotAccessible"
}
