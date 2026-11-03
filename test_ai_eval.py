import unittest

from ai_eval import (
    gabung_skor,
    parse_json_juri,
    skor_kejelasan,
    skor_kejujuran,
    skor_kelengkapan,
    skor_struktur,
)


class TestRubrik(unittest.TestCase):
    def test_kelengkapan_penuh(self):
        self.assertEqual(skor_kelengkapan("tabel baris kolom", ["tabel", "baris", "kolom"]), 5)

    def test_kelengkapan_kosong_minimal_1(self):
        self.assertEqual(skor_kelengkapan("halo", ["tabel", "sql"]), 1)

    def test_kejelasan(self):
        self.assertEqual(skor_kejelasan("kata " * 40, 30, 120), 5)
        self.assertEqual(skor_kejelasan("kata " * 20, 30, 120), 3)
        self.assertEqual(skor_kejelasan("kata", 30, 120), 1)

    def test_struktur_daftar(self):
        self.assertEqual(skor_struktur("1. satu\n2. dua"), 5)

    def test_kejujuran(self):
        self.assertEqual(skor_kejujuran("Ini wajar."), 5)
        self.assertEqual(skor_kejujuran("Dijamin benar dan mutlak."), 1)


class TestJuri(unittest.TestCase):
    def test_parse_valid(self):
        r = parse_json_juri('Ini hasilnya: {"akurasi": 4, "kegunaan": 5, "alasan": "ok"}')
        self.assertEqual(r["akurasi"], 4)

    def test_parse_rusak(self):
        self.assertIsNone(parse_json_juri("bukan json"))

    def test_parse_di_luar_rentang(self):
        self.assertIsNone(parse_json_juri('{"akurasi": 9, "kegunaan": 5}'))

    def test_gabung_skor(self):
        self.assertEqual(gabung_skor(4.0, None), 4.0)
        self.assertEqual(gabung_skor(4.0, {"akurasi": 2, "kegunaan": 2}), 3.0)


if __name__ == "__main__":
    unittest.main()
