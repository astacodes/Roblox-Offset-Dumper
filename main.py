from main.maindumper import main
import win32gui
if __name__ == "__main__":
    s = input("start dumper? (y/n): ").strip().lower()
    if s == "y":
        if win32gui.FindWindow(None, "Roblox"):
            main()
        else:
            print("please join a roblox game before using this thank you!")
    else:
        print("ok :(")