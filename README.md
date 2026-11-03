# AI Eval

Program Python kecil untuk **mengevaluasi kualitas jawaban model AI** dengan rubrik buatan sendiri.

## Fitur
- Kasus uji ada di `cases.json` (mudah ditambah tanpa mengubah kode)
- **Rubrik 4 kriteria** dengan bobot: kelengkapan (40%), kejelasan (20%), struktur (20%), kejujuran (20%)
- **AI sebagai juri** (opsional, `--judge`): model kedua menilai akurasi dan kegunaan, skor digabung 50:50 dengan rubrik
- Mencatat latensi dan jumlah token tiap jawaban
- Keluaran: CSV, JSON, dan `hasil_laporan.md` (rata-rata per kriteria, per kategori, dan jawaban terburuk)
- Ada unit test dan mode `--mock` tanpa API

## Cara pakai
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="kunci-kamu"

python ai_eval.py --mock          # uji coba tanpa API
python ai_eval.py                 # model sungguhan
python ai_eval.py --judge         # tambah penilaian AI-sebagai-juri
python ai_eval.py --model claude-haiku-5-5 --out haiku   # bandingkan model

python -m unittest -v             # jalankan tes
```

## Contoh hasil (tanpa API)
Folder ini menyertakan `contoh_hasil_laporan.md`. **Jawabannya diambil dari chat Claude (claude.ai), bukan dari API**, lalu dinilai oleh program ini lewat mode `--jawaban`. Karena itu latensi dan token tercatat 0.

```bash
python ai_eval.py --jawaban jawaban.json --model "Claude (chat claude.ai, bukan API)" --out contoh_hasil
```
Untuk memakai jawaban AI lain, tempel jawabannya ke `jawaban.json` (kunci = `id` di `cases.json`) dan ganti label `--model` sesuai sumbernya.

## Rubrik
| Kriteria | Cara menilai |
|---|---|
| Kelengkapan | Berapa banyak kata kunci penting di `cases.json` muncul di jawaban |
| Kejelasan | Panjang jawaban masuk rentang `min_kata`-`max_kata` |
| Struktur | Ada daftar bernomor/berpoin, atau minimal beberapa kalimat tertata |
| Kejujuran | Dikurangi jika ada klaim berlebihan ("dijamin", "mutlak", dll.) |

## Keterbatasan
Rubrik berbasis aturan hanya mengukur sinyal permukaan (kata kunci, panjang). Ia tidak memeriksa kebenaran fakta, jadi `--judge` dipakai sebagai pembanding. Ide pengembangan: kasus uji lebih banyak, beberapa juri, dan mengukur kesepakatan antara skor manusia dan skor otomatis.
