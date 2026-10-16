import csv
import os
from models import Elektronik


def muat_data():
    daftar_elektronik = []
    if not os.path.exists("elektronik.csv"):
        print("File elektronik.csv tidak ditemukan.")
        return daftar_elektronik

    with open("elektronik.csv", newline="", encoding="utf-8") as file:
        reader = csv.reader(file)
        next(reader, None)  # Lewati header
        for row in reader:
            elektronik = Elektronik(
                nama_barang=row[0],
                merek=row[1],
                nomor_seri=row[2],
                status=row[3],
            )
            daftar_elektronik.append(elektronik)
    return daftar_elektronik


def tampilkan_elektronik():
    daftar_elektronik = muat_data()
    if not daftar_elektronik:
        print("Tidak ada data elektronik.")
        return

    print("\n=== KATALOG PERANGKAT ELEKTRONIK ===\n")
    print(f"{'Nama Barang':25}{'Merek':20}{'Nomor Seri':20}{'Status'}")
    print("-" * 75)
    for item in daftar_elektronik:
        print(
            f"{item.nama_barang:25}"
            f"{item.merek:20}"
            f"{item.nomor_seri:20}"
            f"{item.status}"
        )
    print("-" * 75)
    print(f"Total Perangkat: {len(daftar_elektronik)}")


def main():
    while True:
        print("\n=== MENU ===")
        print("1. Tampilkan Elektronik")
        print("2. Refresh Data")
        print("0. Keluar")
        pilihan = input("Pilih: ")

        if pilihan == "1":
            tampilkan_elektronik()
        elif pilihan == "2":
            print("Data dimuat ulang...")
            tampilkan_elektronik()
        elif pilihan == "0":
            print("Program selesai.")
            break
        else:
            print("Pilihan tidak valid.")


if __name__ == "__main__":
    import sys

    if "--cli" in sys.argv:
        main()
    else:
        import UI

        UI.main(start_page=2)
