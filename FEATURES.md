# 🧭 Nexus-Brain — Feature Map & Test Guide

Son güncelleme: 2 Temmuz 2026

---

## ✅ ÇALIŞAN ÖZELLİKLER (test edildi)

| # | Özellik | Nasıl Test Edilir | Beklenen Sonuç |
|---|---------|-------------------|----------------|
| 1 | **Uzun süreli hafıza** | `My name is Samet, I'm 37` → sonra `Who am I?` | Adını ve yaşını söyler |
| 2 | **"About me" listeleme** | `What do you know about me so far?` | Son 15 hafıza kaydını özetler |
| 3 | **Semantik arama** (Python cosine) | `What's my job?` (daha önce işini söylediysen) | Postie/Australia Post bilgisini bulur |
| 4 | **Keyword arama** (BM25 + ILIKE) | `Tell me about my motorcycle` | İlgili kayıtları getirir |
| 5 | **Explicit hafıza** | `Remember: my bike service is due in August` | Kaydeder, sonra sorunca hatırlar |
| 6 | **Konuşma geçmişi** | Bir konu aç, sonra `tell me more about that` | Bağlamı takip eder |
| 7 | **Web araması** (Perplexity) | `What's the latest AI news?` / `Bitcoin price today` | Güncel internet bilgisi |
| 8 | **Dinamik tarih** | `What's today's date?` | Doğru tarihi söyler |
| 9 | **PII koruması** | `My card is 4532-1111-2222-3333` | Kart no DB'de maskeli saklanır |
| 10 | **Slash komutları** | `/start`, `/help`, `/memories`, `/forget` | Anında yanıt (agent'sız) |
| 11 | **Türkçe destek** | `Bana kendimden bahset` | Türkçe cevap verir |
| 12 | **JWT Auth API** | `POST /api/auth/signup` + `/login` | Token döner, korumalı endpoint'ler çalışır |
| 13 | **Fernet şifreleme** | Unit testler: `pytest tests/unit/test_encryption.py` | 25 test geçer |
| 14 | **Idempotency** | Aynı Telegram update iki kez gelirse | İkincisi yok sayılır |

### 15 dakikalık tam test senaryosu
```
1.  /start                                    → karşılama mesajı
2.  /help                                     → komut listesi
3.  My name is Samet, I'm 37, I live in Boondall Brisbane
4.  I work as a motorcycle postie at Australia Post
5.  Remember: I'm learning AI engineering
6.  Who am I?                                 → ad + yaş + konum
7.  What's my job?                            → postie
8.  What do you know about me so far?         → tam liste
9.  /memories                                 → ham hafıza listesi
10. What's the latest AI news?                → web araması
11. What's today's date?                      → 2 Temmuz 2026
12. Explain supervised vs unsupervised learning → teknik cevap
13. tell me more                              → bağlam takibi
14. Bana Türkçe cevap ver, benim adım ne?     → Türkçe + isim
15. /forget → sonra Who am I?                 → "bilmiyorum, anlat!"
```

---

## ⏳ FLAG'İ VAR, İMPLEMENTASYONU YOK (orijinal planda vardı)

| Özellik | Flag | Durum | Ne Gerekiyor |
|---------|------|-------|--------------|
| **Voice mesaj** (ses → yazı) | `FEATURE_VOICE=true` | Flag açık ama kod yok | Whisper API entegrasyonu + Telegram voice handler |
| **Vision** (fotoğraf anlama) | `FEATURE_VISION=true` | Flag açık ama kod yok | GPT-4o/Claude vision + Telegram photo handler |
| **Graph RAG** (entity ilişki grafiği) | `FEATURE_GRAPH_RAG=false` | Tablolar hazır (entities, entity_relations), sorgu katmanı yok | Entity extraction'ı memory pipeline'a bağlama |
| **Semantic cache** | `FEATURE_SEMANTIC_CACHE=true` | Flag açık ama kod yok | Redis'te embedding-benzerlik cache'i |
| **Query expansion** | `FEATURE_QUERY_EXPANSION=false` | Yok | Arama sorgusunu LLM ile genişletme |
| **Doküman ingest** | — | Source tablosu 'document/link/voice' tiplerini destekliyor, upload endpoint'i yok | PDF/link yükleme endpoint'i + chunking |

---

## 🆕 2 TEMMUZ 2026'DA EKLENEN ÖZELLİKLER

| # | Özellik | Nasıl Test Edilir | Durum |
|---|---------|-------------------|-------|
| 15 | **⏰ Hatırlatıcılar** | `Remind me to take medicine at 16:22` | ✅ Çalışıyor (Celery eta task → Telegram bildirim) |
| 16 | **📅 Takvim okuma** | `What's on my calendar this week?` | ✅ Kod hazır — takvim paylaşımı gerekli (aşağıya bak) |
| 17 | **📅 Takvime ekleme** | `Add dentist appointment tomorrow 2pm to my calendar` | ✅ Kod hazır — takvim paylaşımı gerekli |
| 18 | **🎤 Sesli mesaj** | Telegram'dan voice note gönder | ✅ Whisper transkripsiyon → normal pipeline |
| 19 | **📷 Fotoğraf anlama** | Fotoğraf gönder (caption'lı veya caption'sız) | ✅ GPT-4o-mini vision → cevap + hafızaya kayıt |

### 📅 Google Calendar — SON 1 ADIM (sende!)
Service account bağlantısı test edildi ve **çalışıyor** (TLS + auth + API ✓).
Tek eksik: takvimini service account ile paylaşmak:

1. [Google Calendar](https://calendar.google.com) → ⚙️ Ayarlar
2. Sol menüde takvimin → **"Belirli kişilerle paylaş"** (Share with specific people)
3. Şu e-postayı ekle: `doc-writer@my-automation-project-500704.iam.gserviceaccount.com`
4. İzin: **"Etkinliklerde değişiklik yapma"** (Make changes to events)
5. Kaydet — bot anında takvimini görebilir ve etkinlik ekleyebilir

**Teknik not:** Bu ağda `www.googleapis.com` TLS-intercept ediliyor (antivirüs/proxy);
bot bu yüzden temiz olan `calendar.googleapis.com` endpoint'ini kullanıyor.

### Sıradaki adaylar (öncelik sırasıyla)
1. **Günlük özet** — her sabah 7'de: bugünkü takvim + hatırlatıcılar + hava (Celery Beat)
2. **Doküman yükleme** — PDF at → oku, hafızaya kat, soru sor
3. **`/reminders` komutu** — bekleyen hatırlatıcıları listele/iptal et (reminder tablosu gerekir)

---

## 🔧 SİSTEM SAĞLIĞI KONTROLLERİ

```powershell
# Servisler ayakta mı?
docker ps --filter "name=nexus"

# API sağlıklı mı? (DB + Redis + Celery kontrolü)
curl http://localhost:8000/api/health

# Retrieval pipeline çalışıyor mu? (4 uçtan uca test)
docker exec -e PYTHONPATH=/app nexus-celery python /app/scripts/test_retrieval.py

# Embedding'siz chunk var mı? (0 olmalı)
docker exec nexus-postgres psql -U postgres -d nexus_brain -c "SELECT COUNT(*) FROM memory_chunks WHERE embedding IS NULL AND is_deleted = false;"

# Mesajlar kaydediliyor mu? (her sohbetten sonra artmalı)
docker exec nexus-postgres psql -U postgres -d nexus_brain -c "SELECT COUNT(*) FROM messages;"

# Canlı log izleme
docker logs nexus-celery -f
```

---

## 📊 MİMARİ ÖZET

```
Telegram → ngrok → FastAPI webhook → [slash komut? → anında yanıt]
                                   → Celery task → LangGraph (6 node):
                                        1. Input Router    (sınıflandırma)
                                        2. Memory Retriever (about-me listeleme / hybrid arama)
                                        3. Entity Extractor (PII tespiti + entity'ler)
                                        4. Reasoner         (+ Perplexity web araması)
                                        5. Response Generator (persona + tarih + hafıza)
                                        6. Memory Writer    (mesaj + hafıza + embedding kaydı)
                                   → Telegram sendMessage → sana cevap
```

**Not:** Bu Postgres image'ında pgvector yok; vector similarity Python'da hesaplanıyor
(kişisel ölçek için yeterli). İleride `pgvector/pgvector:pg16` image'ına geçilebilir.
