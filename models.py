class Elektronik:

    def __init__(self, nama_barang, merek, nomor_seri, status="Tersedia"):
        self.nama_barang = nama_barang
        self.merek = merek
        self.nomor_seri = nomor_seri
        self.status = status

    def to_list(self):
        return [self.nama_barang, self.merek, self.nomor_seri, self.status]

    def __str__(self):
        return f"{self.nama_barang} ({self.merek}) - SN: {self.nomor_seri} [{self.status}]"


class Pengguna:

    def __init__(self, id_pengguna, nama, divisi, no_hp):
        self.id = id_pengguna
        self.nama = nama
        self.divisi = divisi
        self.no_hp = no_hp

    def to_list(self):
        return [self.id, self.nama, self.divisi, self.no_hp]

    def __str__(self):
        return f"{self.nama} ({self.id}) - Divisi {self.divisi}"