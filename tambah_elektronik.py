import csv
import os
from models import Elektronik


def simpan_elektronik():
    print("\n=== TAMBAH DATA ELEKTRONIK ===")
    nama_barang = input("Nama Barang : ").strip()
    merek = input("Merek       : ").strip()
    nomor_seri = input("Nomor Seri  : ").strip()

    if not nama_barang or not merek or not nomor_seri:
        print("\n[PERINGATAN] Semua kolom harus diisi!\n")
        return

    elektronik = Elektronik(nama_barang, merek, nomor_seri)
    file_exists = os.path.exists("elektronik.csv")

    with open("elektronik.csv", "a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Nama Barang", "Merek", "Nomor Seri", "Status"])
        writer.writerow(elektronik.to_list())

    print("\n[BERHASIL] Data elektronik berhasil ditambahkan.\n")


def main():
    while True:
        print("=== MENU TAMBAH ELEKTRONIK ===")
        print("1. Tambah Elektronik")
        print("0. Keluar")
        pilihan = input("Pilih menu: ")

        if pilihan == "1":
            simpan_elektronik()
        elif pilihan == "0":
            print("Program selesai.")
            break
        else:
            print("Pilihan tidak valid.\n")


if __name__ == "__main__":
    import sys

    if "--cli" in sys.argv:
        main()
    else:
        import UI

        UI.main(start_page=1)
