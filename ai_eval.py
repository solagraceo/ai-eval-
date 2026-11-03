"""
ai_eval.py - Evaluator jawaban model AI dengan rubrik buatan sendiri.

Alur:
  cases.json -> tanya model -> nilai pakai rubrik (aturan) -> [opsional]
  nilai pakai AI sebagai juri -> simpan CSV + JSON -> buat laporan.md

Contoh:
  python ai_eval.py --mock               # tanpa API, untuk uji coba
  python ai_eval.py                      # model sungguhan
  python ai_eval.py --judge              # tambah penilaian AI-sebagai-juri
  python ai_eval.py --model claude-haiku-5-5 --out hasil
  python ai_eval.py --jawaban jawaban.json --model "Claude (chat)"   # tanpa API
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

DEFAULT_MODEL = os.getenv("MODEL", "claude-sonnet-5-5")

# Bobot rubrik (total = 1.0). Ubah sesuai prioritasmu.
BOBOT = {"kelengkapan": 0.4, "kejelasan": 0.2, "struktur": 0.2, "kejujuran": 0.2}

# Klaim berlebihan yang mengurangi skor kejujuran.
OVERCLAIM = ["pasti 100%", "dijamin", "tidak mungkin salah", "mutlak", "selalu benar"]

JUDGE_PROMPT = """Kamu adalah penilai jawaban AI yang ketat tapi adil.

Pertanyaan:
{pertanyaan}

Jawaban yang dinilai:
{jawaban}

Beri nilai bilangan bulat 1-5 untuk:
- akurasi: apakah isinya benar secara faktual
- kegunaan: apakah menjawab pertanyaan dan mudah dipahami pemula

Balas HANYA dengan JSON, tanpa teks lain:
{{"akurasi": <1-5>, "kegunaan": <1-5>, "alasan": "<satu kalimat>"}}"""


# ---------------------------------------------------------------- Rubrik ---

def skor_kelengkapan(jawaban: str, keywords: list[str]) -> int:
    """Semakin banyak kata kunci penting muncul, semakin tinggi."""
    if not keywords:
        return 5
    teks = jawaban.lower()
    ketemu = sum(1 for k in keywords if k.lower() in teks)
    return max(1, round(ketemu / len(keywords) * 5))


def skor_kejelasan(jawaban: str, min_kata: int, max_kata: int) -> int:
    """Panjang jawaban sesuai target. Toleransi 50% di luar rentang."""
    n = len(jawaban.split())
    if min_kata <= n <= max_kata:
        return 5
    if min_kata * 0.5 <= n <= max_kata * 1.5:
        return 3
    return 1


def skor_struktur(jawaban: str) -> int:
    """Daftar bernomor/berpoin atau beberapa kalimat yang tertata."""
    ada_daftar = bool(re.search(r"^\s*(\d+[.)]|[-*•])\s", jawaban, re.MULTILINE))
    kalimat = len(re.findall(r"[.!?](\s|$)", jawaban))
    if ada_daftar:
        return 5
    if kalimat >= 3:
        return 4
    if kalimat >= 2:
        return 3
    return 1


def skor_kejujuran(jawaban: str) -> int:
    """Kurangi 2 poin untuk setiap klaim berlebihan."""
    teks = jawaban.lower()
    pelanggaran = sum(1 for w in OVERCLAIM if w in teks)
    return max(1, 5 - 2 * pelanggaran)


def nilai_rubrik(jawaban: str, kasus: dict) -> tuple[dict, float]:
    skor = {
        "kelengkapan": skor_kelengkapan(jawaban, kasus.get("keywords", [])),
        "kejelasan": skor_kejelasan(
            jawaban, kasus.get("min_kata", 30), kasus.get("max_kata", 150)
        ),
        "struktur": skor_struktur(jawaban),
        "kejujuran": skor_kejujuran(jawaban),
    }
    total = round(sum(skor[k] * BOBOT[k] for k in BOBOT), 2)
    return skor, total


# ---------------------------------------------------------- Klien model ---

class ModelClient:
    """Pembungkus API dengan retry sederhana."""

    def __init__(self, model: str, retries: int = 3):
        import anthropic  # diimpor di sini agar --mock tidak butuh library

        self.client = anthropic.Anthropic()  # baca ANTHROPIC_API_KEY
        self.model = model
        self.retries = retries

    def ask(self, prompt: str, max_tokens: int = 600) -> tuple[str, float, int]:
        for percobaan in range(1, self.retries + 1):
            try:
                mulai = time.perf_counter()
                r = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                durasi = time.perf_counter() - mulai
                teks = "".join(b.text for b in r.content if b.type == "text")
                token = r.usage.input_tokens + r.usage.output_tokens
                return teks.strip(), round(durasi, 2), token
            except Exception as e:  # noqa: BLE001
                if percobaan == self.retries:
                    raise
                jeda = 2 ** percobaan
                print(f"  ! error ({e}); coba lagi dalam {jeda} detik")
                time.sleep(jeda)
        raise RuntimeError("tidak tercapai")


class MockClient:
    """Jawaban palsu bervariasi supaya rubrik bisa diuji tanpa API."""

    JAWABAN = {
        "db-01": (
            "Basis data relasional menyimpan data dalam tabel yang terdiri dari "
            "baris dan kolom. Antar tabel dihubungkan lewat relasi memakai kunci. "
            "Data biasanya diakses dengan bahasa SQL."
        ),
        "hw-01": "RAM itu cepat.",
        "si-01": (
            "1. Efisiensi proses bisnis karena pekerjaan manual jadi otomatis.\n"
            "2. Pengambilan keputusan lebih baik karena data dan informasi akurat.\n"
            "3. Koordinasi antar bagian jadi lebih mudah dan terdokumentasi."
        ),
        "ai-01": (
            "Halusinasi adalah saat model menjawab dengan yakin tetapi isinya salah. "
            "Hasilnya dijamin benar dan mutlak, katanya."
        ),
    }

    def __init__(self):
        self.model = "mock"
        self._kasus_id = None

    def set_kasus(self, kasus_id: str):
        self._kasus_id = kasus_id

    def ask(self, prompt: str, max_tokens: int = 600) -> tuple[str, float, int]:
        if prompt.startswith("Kamu adalah penilai"):
            return '{"akurasi": 4, "kegunaan": 4, "alasan": "Mock juri."}', 0.0, 0
        return self.JAWABAN.get(self._kasus_id, "Jawaban contoh."), 0.0, 0


class ManualClient:
    """Baca jawaban dari file JSON {id: jawaban}. Gratis, tanpa API.

    Cocok kalau jawaban AI diambil sendiri dari chat biasa lalu ditempel
    ke file. Isi `label` dengan sumber jawaban agar laporan jujur.
    """

    def __init__(self, path: str, label: str):
        self.jawaban = json.loads(Path(path).read_text(encoding="utf-8"))
        self.model = label
        self._kasus_id = None

    def set_kasus(self, kasus_id: str):
        self._kasus_id = kasus_id

    def ask(self, prompt: str, max_tokens: int = 600) -> tuple[str, float, int]:
        if prompt.startswith("Kamu adalah penilai"):
            raise RuntimeError("--judge tidak bisa dipakai bersama --jawaban")
        return self.jawaban[self._kasus_id].strip(), 0.0, 0


# ------------------------------------------------------------- AI juri ---

def parse_json_juri(teks: str) -> dict | None:
    """Ambil objek JSON pertama dari balasan juri, toleran pada teks tambahan."""
    cocok = re.search(r"\{.*\}", teks, re.DOTALL)
    if not cocok:
        return None
    try:
        data = json.loads(cocok.group())
        akurasi, kegunaan = int(data["akurasi"]), int(data["kegunaan"])
    except (ValueError, KeyError, TypeError):
        return None
    if not (1 <= akurasi <= 5 and 1 <= kegunaan <= 5):
        return None
    return {
        "akurasi": akurasi,
        "kegunaan": kegunaan,
        "alasan": str(data.get("alasan", "")),
    }


def nilai_juri(client, pertanyaan: str, jawaban: str) -> dict | None:
    teks, _, _ = client.ask(
        JUDGE_PROMPT.format(pertanyaan=pertanyaan, jawaban=jawaban), max_tokens=300
    )
    return parse_json_juri(teks)


# --------------------------------------------------------------- Hasil ---

@dataclass
class Hasil:
    waktu: str
    id: str
    kategori: str
    model: str
    pertanyaan: str
    jawaban: str
    kelengkapan: int
    kejelasan: int
    struktur: int
    kejujuran: int
    skor_rubrik: float
    juri_akurasi: int | None
    juri_kegunaan: int | None
    juri_alasan: str
    skor_akhir: float
    latensi_detik: float
    token: int


def gabung_skor(skor_rubrik: float, juri: dict | None) -> float:
    """Tanpa juri: skor rubrik. Dengan juri: rata-rata rubrik dan juri 50:50."""
    if not juri:
        return skor_rubrik
    skor_juri = (juri["akurasi"] + juri["kegunaan"]) / 2
    return round(skor_rubrik * 0.5 + skor_juri * 0.5, 2)


def evaluasi(kasus: dict, client, pakai_juri: bool) -> Hasil:
    if hasattr(client, "set_kasus"):
        client.set_kasus(kasus["id"])
    jawaban, durasi, token = client.ask(kasus["pertanyaan"])
    skor, skor_rubrik = nilai_rubrik(jawaban, kasus)
    juri = nilai_juri(client, kasus["pertanyaan"], jawaban) if pakai_juri else None
    return Hasil(
        waktu=datetime.now().isoformat(timespec="seconds"),
        id=kasus["id"],
        kategori=kasus.get("kategori", "umum"),
        model=client.model,
        pertanyaan=kasus["pertanyaan"],
        jawaban=jawaban,
        **skor,
        skor_rubrik=skor_rubrik,
        juri_akurasi=juri["akurasi"] if juri else None,
        juri_kegunaan=juri["kegunaan"] if juri else None,
        juri_alasan=juri["alasan"] if juri else "",
        skor_akhir=gabung_skor(skor_rubrik, juri),
        latensi_detik=durasi,
        token=token,
    )


# ------------------------------------------------------------- Laporan ---

def buat_laporan(hasil: list[Hasil]) -> str:
    rata = lambda xs: round(statistics.mean(xs), 2) if xs else 0.0  # noqa: E731
    baris = [
        "# Laporan Evaluasi AI",
        "",
        f"- Model: `{hasil[0].model}`",
        f"- Jumlah kasus: {len(hasil)}",
        f"- Skor akhir rata-rata: **{rata([h.skor_akhir for h in hasil])}/5**",
        f"- Latensi rata-rata: {rata([h.latensi_detik for h in hasil])} detik",
        "",
        "## Rata-rata per kriteria",
        "",
        "| Kriteria | Skor |",
        "|---|---|",
    ]
    for k in BOBOT:
        baris.append(f"| {k} | {rata([getattr(h, k) for h in hasil])} |")

    baris += ["", "## Per kategori", "", "| Kategori | Skor akhir |", "|---|---|"]
    for kat in sorted({h.kategori for h in hasil}):
        baris.append(
            f"| {kat} | {rata([h.skor_akhir for h in hasil if h.kategori == kat])} |"
        )

    baris += ["", "## Jawaban dengan skor terendah", ""]
    for h in sorted(hasil, key=lambda x: x.skor_akhir)[:3]:
        baris.append(f"- **{h.id}** ({h.skor_akhir}/5): {h.pertanyaan}")
        if h.juri_alasan:
            baris.append(f"  - Catatan juri: {h.juri_alasan}")
    return "\n".join(baris) + "\n"


def simpan(hasil: list[Hasil], prefix: str) -> None:
    baris = [asdict(h) for h in hasil]
    with open(f"{prefix}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(baris[0].keys()))
        w.writeheader()
        w.writerows(baris)
    Path(f"{prefix}.json").write_text(
        json.dumps(baris, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    Path(f"{prefix}_laporan.md").write_text(buat_laporan(hasil), encoding="utf-8")


# ---------------------------------------------------------------- Main ---

def main() -> None:
    p = argparse.ArgumentParser(description="Evaluator jawaban AI")
    p.add_argument("--cases", default="cases.json", help="file kasus uji")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--out", default="hasil", help="awalan nama file keluaran")
    p.add_argument("--judge", action="store_true", help="tambah AI sebagai juri")
    p.add_argument("--mock", action="store_true", help="tanpa API (uji coba)")
    p.add_argument(
        "--jawaban",
        help="file JSON berisi jawaban {id: teks}; tanpa API. "
        "Isi --model dengan sumber jawaban, mis. 'Claude (chat)'",
    )
    args = p.parse_args()

    kasus_list = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    if args.mock:
        client = MockClient()
    elif args.jawaban:
        client = ManualClient(args.jawaban, args.model)
    else:
        client = ModelClient(args.model)

    hasil: list[Hasil] = []
    for i, kasus in enumerate(kasus_list, 1):
        h = evaluasi(kasus, client, args.judge)
        hasil.append(h)
        print(f"[{i}/{len(kasus_list)}] {h.id}: {h.skor_akhir}/5")

    simpan(hasil, args.out)
    rata = statistics.mean(h.skor_akhir for h in hasil)
    print(f"\nRata-rata: {rata:.2f}/5")
    print(f"Tersimpan: {args.out}.csv, {args.out}.json, {args.out}_laporan.md")


if __name__ == "__main__":
    main()
