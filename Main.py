import subprocess
import sys


def buka_tambah_elektronik():
    subprocess.run([sys.executable, "tambah_elektronik.py", "--cli"])


def buka_tampil_elektronik():
    subprocess.run([sys.executable, "tampil_elektronik.py", "--cli"])


def menu_utama():
    while True:
        print("\n" + "=" * 40)
        print(" KATALOG ELEKTRONIK ".center(40, "="))
        print("=" * 40)
        print("1. Tambah Elektronik")
        print("2. Tampilkan Elektronik")
        print("0. Keluar")
        print("=" * 40)

        pilihan = input("Pilih menu: ")

        if pilihan == "1":
            buka_tambah_elektronik()
        elif pilihan == "2":
            buka_tampil_elektronik()
        elif pilihan == "0":
            print("Terima kasih.")
            break
        else:
            print("Pilihan tidak valid!")


if __name__ == "__main__":
    import sys

    if "--cli" in sys.argv:
        menu_utama()
    else:
        import UI

        UI.main(start_page=0)
