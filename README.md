# HP Test — ishga qabul qilish uchun test tizimi

Ichki tarmoqda ishlaydi, internet talab qilmaydi. Nomzodlar testni **Safe Exam Browser (SEB)** orqali yechadi.

## Rollar

| Rol | Nima qiladi | Nimani ko'radi |
|---|---|---|
| **Superadmin** | Foydalanuvchilarni yaratadi, nomzodlar ro'yxatini yuritadi, testga ekspertlar biriktiradi, suhbat va himoya ballarini kiritadi, natijalarni Excel'ga yuklaydi | Hammasini: F.I.Sh., javoblar, har bir ekspertning mezon bo'yicha ballari |
| **Test tuzuvchi** | Savollar bazasini yuritadi, test → bloklar → savollar (bazadan yoki yangi) tuzadi | Testlar va baza (kalit, mezonlar bilan) |
| **Tekshiruvchi (ekspert)** | O'ziga biriktirilgan yozma ishlarni mezonlar bo'yicha baholaydi | Faqat anonim kod (`K-434563`). Nomzod ismi va boshqa ekspertning bali ko'rinmaydi |
| **Nomzod** | Ro'yxatda bo'lsa, F.I.Sh. + tug'ilgan sana bilan kiradi va testni yechadi | Faqat savollar. Kalit va mezonlar ko'rsatilmaydi |

## Tanlov materiallari (Hisob palatasi)

Materiallar `.docx` fayldan yuklanadi. **Eng oson yo'li — veb-sahifa:** «Саволлар базаси» → **«Ҳужжатдан юклаш (.docx)»**. Avval fayl tekshiriladi va nima yuklanishi ko'rsatiladi, tasdiqlangandan keyin bazaga yoziladi. Shu formatdagi boshqa hujjatlarni ham shu yerdan yuklaysiz: har bir hujjat o'z nomi (manba) ostida saqlanadi, qayta yuklansa savollar kod bo'yicha yangilanadi. Format qoidalari sahifaning o'zida va `exam/importer.py` boshida yozilgan.

Yoki buyruq bilan:

```bash
.venv/bin/python manage.py import_tanlov /path/Hisob_palatasi_tanlov_materiallari_uz_kirill.docx
# Docker'da:
docker compose cp fayl.docx web:/tmp/t.docx
docker compose exec web python manage.py import_tanlov /tmp/t.docx
```

Yaratiladi:

| Bo'lim (Саволлар базаси) | Tarkibi |
|---|---|
| Молиявий аудитор — амалий топшириқлар | МА 01–50, har biri 5 mezon × 0–2 ball = 10 ball |
| Тизимли таҳлилчи — амалий топшириқлар | ТА 01–50, xuddi shunday |
| Мантиқий тест — 1…5-тўплам | Har biri 20 savol, А–Д variant, kalit va izoh bilan (1 ball) |
| Суҳбат — umumiy / auditor / tahlilchi | С 01–12, С 13–16, С 17–20, har biri 5 mezon |

Shuningdek ikkita **namuna test** (nofaol) yaratiladi:

| Test | Mantiqiy test (40 daq.) | Yozma amaliy (180 daq., 6 topshiriq) | Suhbat (5 savol) |
|---|---|---|---|
| Молиявий аудитор | 1-to'plam | МА 01, 05, 21, 30, 38, 46 | С 01, 02, 03, 13, 14 |
| Тизимли таҳлилчи | 2-to'plam | ТА 01, 11, 20, 22, 36, 42 | С 01, 02, 03, 17, 18 |

Biletdagi topshiriqlarni hujjat tavsiyasiga ko'ra tanladim: auditor uchun hisob-kitob, dalil va tanlanma, nazorat, xulosa va tavsiya; tahlilchi uchun talablar, ma'lumotlar, integratsiya, nazorat va sinov. **Komissiya ularni ko'rib chiqib, tasdiqlashi yoki almashtirishi kerak**: test sahifasida "+ Базадан" orqali qo'shiladi, savoldagi "×" orqali olib tashlanadi. Buyruqni qayta ishga tushirish xavfsiz: baza yangilanadi, testlar o'zgarmaydi.

## Baholash qoidalari (hujjat bo'yicha)

1. **Mantiqiy test** — kalit bo'yicha avtomatik: to'g'ri javob 1 ball, noto'g'ri yoki bo'sh 0. Manfiy ball yo'q.
   Talqin (20 ballik): 0–7 — sezilarli qiyinchilik, 8–13 — qisman, 14–17 — yaxshi, 18–20 — yuqori. Bu IQ o'lchovi emas.
2. **Yozma amaliy topshiriq** — har mezon 0 / 1 / 2 ball, ekspert har javob uchun ballning qisqa asosini yozadi.
   - Test sozlamasida **"Ikki mustaqil ekspert"** tanlangan bo'lsa, test tugashi bilan ish eng kam band bo'lgan ikki ekspertga avtomatik beriladi. Ular bir-birining balini ko'rmaydi.
   - Ekspertlar jami bali farqi maksimalning **15 foizidan** oshsa (60 dan 9) yoki biror mezonda biri **0**, ikkinchisi **2** qo'ysa, tizim **uchinchi ekspertni** avtomatik tayinlaydi. Natija har mezon bo'yicha uch bahoning **medianasi** bo'ladi.
   - Uchinchi tekshiruv bo'lmasa, ikki baho o'rtachasi olinadi.
   - Ekspert "Yakunlash va topshirish" ni bosgandan keyin bahoni o'zgartira olmaydi. Superadmin uni "Qayta ochish" mumkin.
   - Javob berilmagan topshiriq avtomatik 0 oladi va ekspertga ko'rsatilmaydi.
3. **Suhbat** — komissiya nomzod natija sahifasida har savolning 5 mezoni bo'yicha 0–2 ball kiritadi (5 savol × 10 = 50).
4. **Amaliy ish himoyasi** — superadmin 0–15 ball kiritadi.
5. **Yakuniy ball (100)** = 55 × amaliy/60 + 15 × mantiqiy/20 + 15 × suhbat/50 + himoya.
   Vaznlarni test sozlamalarida o'zgartirish mumkin, yig'indisi 100 bo'lishi shart.

> Ikki ekspert rejimi uchun testga kamida 2 ta, uchinchi tekshiruv uchun 3 ta tekshiruvchi biriktiring.
> Bitta ekspert yetarli bo'lsa, test sozlamasida "Bitta ekspert" ni tanlang.

## Qanday ishlaydi

1. **Test tuzuvchi** namuna testni ko'rib chiqadi, kerak bo'lsa topshiriqlarni almashtiradi va testni **Фаол** qiladi.
2. **Superadmin** testga ekspertlarni biriktiradi va **Номзодлар** sahifasida nomzodlarni testga yozadi: qo'lda yoki Excel'dan (ustunlar: Фамилия, Исм, Отасининг исми, Туғилган сана; namuna faylni o'sha sahifadan olish mumkin).
3. **Nomzod** faqat F.I.Sh. va tug'ilgan sanasini yozadi — tizim uning testini o'zi topadi. Ro'yxatda yo'q odam kira olmaydi. Nomzodga bir nechta faol test biriktirilgan bo'lsa, qaysi birini boshlashni tanlaydi. Keyin testni yechadi:
   - Bloklar ketma-ket ochiladi, har birining o'z taymeri bor. Vaqt **serverda** hisoblanadi.
   - Savollar aralashtiriladi. Variantlar А–Д tartibida qoladi, chunki ba'zi variantlar boshqa harflarga havola qiladi.
   - Har bir javob darhol serverga saqlanadi. Kompyuter o'chib qolsa, nomzod qayta kirib davom etadi.
   - Yopilgan blokka qaytib bo'lmaydi. Bitta testni ikki marta topshirib bo'lmaydi.

Interfeys o'zbek tilida, kirill yozuvida.
4. **Ekspertlar** yozma ishlarni baholaydi. **Superadmin** suhbat va himoya ballarini kiritadi.
5. **Superadmin** yakuniy natijalarni ko'radi va Excel'ga yuklaydi.

Superadmin qo'shimcha amallari: vaqt qo'shish, testni majburan yakunlash, ekspert qo'shish yoki olib tashlash, ekspert tekshiruvini qayta ochish, urinishni o'chirish (qayta topshirishga ruxsat).

---

## Serverga o'rnatish (Docker)

Server — ichki tarmoqdagi istalgan Linux (yoki Windows/macOS) kompyuter, unda Docker bo'lsin. Internet faqat birinchi yig'ishda (paketlarni yuklash uchun) kerak.

```bash
git clone https://github.com/dilshod97/hp_test.git
cd hp_test
cp .env.example .env
nano .env                         # SERVER_IP, parollar
docker compose up -d --build
```

Shundan keyin:
- Xodimlar: `https://SERVER_IP/staff/` (portni o'zgartirgan bo'lsangiz: `https://SERVER_IP:PORT/staff/`)
- Nomzodlar (SEB start URL): `https://SERVER_IP/exam/`
- Superadmin — `.env` dagi `SUPERADMIN_USERNAME` / `SUPERADMIN_PASSWORD`

Birinchi ishga tushishda avtomatik:
- baza jadvallari yaratiladi, superadmin qo'shiladi;
- `SERVER_IP` uchun **ichki HTTPS sertifikati** yaratiladi (domen shart emas) va `certs/` papkasiga yoziladi;
- maxfiy kalit yaratilib, saqlanadi.

**Tanlov materiallarini yuklash** (savollar bazasi va namuna testlar):
```bash
docker compose cp Hisob_palatasi_tanlov_materiallari_uz_kirill.docx web:/tmp/t.docx
docker compose exec web python manage.py import_tanlov /tmp/t.docx
```
> Materiallar hujjati (javob kalitlari bilan) repozitoriyaga **qo'yilmaydi** — uni serverga alohida ko'chiring.

**Yangilash:** `git pull && docker compose up -d --build`
**Zaxira nusxa:**
```bash
docker compose exec db pg_dump -U hp_test hp_test > backup_$(date +%F).sql
docker run --rm -v hp_test_media:/m -v "$PWD":/b alpine tar czf /b/media_$(date +%F).tgz -C /m .
```

### HTTPS sertifikati va test kompyuterlari
Veb-kamera faqat HTTPS'da ishlaydi, shuning uchun tizim HTTPS bilan ishga tushadi. Sertifikat bizning ichki "sertifikat markazimiz" tomonidan chiqariladi — test kompyuterlari unga ishonishi kerak:

- **Eng qulay:** SEB Config Tool → **Network → Certificates** → `certs/ca.crt` ni qo'shing (Embed / Use as CA). Shunda sertifikat `.seb` fayl ichida bo'ladi, kompyuterlarga alohida o'rnatish shart emas.
- **Yoki** har bir kompyuterga bir marta: Windows — `ca.crt` ni ikki marta bosing → *Install Certificate* → *Local Machine* → *Trusted Root Certification Authorities*. macOS — *Keychain Access* → *System* → faylni tashlang → *Always Trust*.
- Xodimlar brauzerida ham shunday o'rnatilsa, "xavfsiz emas" ogohlantirishi chiqmaydi.
- Server IP manzili o'zgarsa: `certs/` ni o'chirib, `.env` da `SERVER_IP` ni yangilang va `docker compose restart web`.

`certs/ca.key` — markaz kaliti, uni hech kimga bermang va repozitoriyaga qo'ymang.

### Docker'siz lokal ishga tushirish (sinov uchun)
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py create_superadmin --username admin --password 'Parol12345'
.venv/bin/python manage.py runserver 0.0.0.0:8090          # HTTP, SEB tekshiruvi o'chiq
# yoki HTTPS bilan (kamera uchun):
sh scripts/make_certs.sh 10.42.0.231 && sh scripts/run_https.sh 8443
```
Avtomatik testlar: `.venv/bin/python manage.py test exam`

---

## Nomzod rasmi (veb-kamera)
Test sozlamasida **«Номзоднинг расмини олиш»** yoqilgan bo'lsa, nomzod testni boshlashdan oldin rozilik beradi va bir marta rasmga tushadi.
- Kamera bo'lmasa yoki nomzod rozi bo'lmasa — test rasmsiz davom etadi, natijada sababi ko'rinadi.
- Rasmni **faqat superadmin** ko'radi (natijalar ro'yxati va nomzod sahifasi). Ekspertlarga ko'rsatilmaydi.
- Rasmlar `PHOTO_RETENTION_DAYS` (standart 180) kundan keyin avtomatik o'chiriladi; urinish o'chirilsa rasm ham o'chadi.
- SEB'da kameraga ruxsat bering (SEB Config Tool → Browser/Security bo'limidagi camera/microphone sozlamasi).

## Nomzod kompyuterlarini sozlash (Windows / macOS)

### 1. Safe Exam Browser o'rnatish
SEB'ni rasmiy saytdan (safeexambrowser.org) yuklab oling va har bir test kompyuteriga o'rnating. SEB **Windows, macOS va iPad** uchun bor; macOS versiyasi Mac App Store'da ham mavjud. Bitta `.seb` fayl ikkalasida ishlaydi. Mac'da taqiqlangan dasturlar bundle ID bilan yoziladi (masalan `com.apple.calculator`, `com.microsoft.Excel`, `com.google.Chrome`, `com.apple.Safari`).

### 2. Sozlama faylini (`.seb`) tayyorlash
Bu ish bir marta, admin kompyuterida qilinadi. **SEB Config Tool** ni oching:

| Bo'lim | Sozlama |
|---|---|
| **General** | Start URL: `https://SERVER_IP/exam/` |
| **General** | Administrator password va **Quit/unlock password** qo'ying. Faqat nazoratchi bilsin |
| **Config File** | "Use SEB settings file for: **starting an exam**" |
| **User Interface** | Browser view mode: **Use full screen mode** |
| **Browser** | Yangi oyna ochishni bloklang |
| **Down/Uploads** | Yuklab olish va yuklashni o'chiring |
| **Exam** | "Use Browser Exam Key and Config Key" ni yoqing (4-qadam uchun). Ekrandagi **Config Key** ni nusxalab oling |
| **Applications** | "Allow switching to third party applications" — **o'chiq**. Prohibited processes ro'yxatiga kerak bo'lsa `calc.exe`, `excel.exe`, `chrome.exe`, `msedge.exe`, `firefox.exe`, `winword.exe`, `telegram.exe` ni qo'shing |
| **Network → Filter** | URL filter'ni yoqing va faqat `https://SERVER_IP/*` ga ruxsat bering |
| **Network → Certificates** | `certs/ca.crt` ni qo'shing (HTTPS sertifikatiga ishonish uchun) |
| **Security** | Virtual mashinada ishlashni taqiqlang, screen capture/sharing'ni o'chiring |
| **Registry** (Windows) | Task Manager, Lock, Switch user, Log off, Sign out ni o'chiring |

Faylni `test.seb` nomi bilan saqlang va har bir test kompyuterining ish stoliga qo'ying.
Bo'lim nomlari SEB versiyasiga qarab biroz farq qilishi mumkin.

### 3. Server tomonda SEB'ni majburiy qilish
Docker'da (`DEBUG=false`) bu **standart holatda yoqiq**: `/exam/` sahifalari oddiy brauzerdan ochilmaydi, "Кириш мумкин эмас" chiqadi. Xodimlarning `/staff/` sahifalariga bu ta'sir qilmaydi.
Lokal sinovda (`DEBUG=true`) tekshiruv o'chiq, shuning uchun oddiy brauzerda sinab ko'rish mumkin. Majburan yoqish yoki o'chirish: `.env` da `REQUIRE_SEB=true` / `false`.

### 4. (Tavsiya) Config Key bilan qattiq tekshiruv
`REQUIRE_SEB=true` faqat brauzer nomini tekshiradi. Uni qalbakilashtirish mumkin. Qattiqroq tekshiruv uchun 2-qadamda olingan Config Key'ni yozing:
```
SEB_CONFIG_KEYS=bu_yerga_config_key
```
Shunda server faqat aynan sizning `.seb` faylingiz bilan ochilgan SEB'ni qabul qiladi. `.seb` faylni har gal o'zgartirganingizda Config Key ham o'zgaradi, uni `.env` da yangilang va `docker compose up -d` qiling.

### 5. Qo'shimcha himoya
- **Tarmoq:** router yoki firewall'da test kompyuterlariga faqat server IP manziliga chiqishga ruxsat bering.
- **Alohida Windows foydalanuvchisi** ("Test", admin huquqisiz). Unga kirganda `test.seb` avtomatik ochilsin: faylni `shell:startup` papkasiga qo'ying.
- **Telefonlarni** test oldidan yig'ib oling.
- Testdan keyin nazoratchi **Quit password** bilan SEB'ni yopadi.

### Test kuni tartibi
1. Test **Фаол** qilinadi, nomzodlar **Номзодлар** ro'yxatiga kiritilgan bo'ladi.
2. Nazoratchi kompyuterlarda `test.seb` ni ochib qo'yadi.
3. Nomzodlar F.I.Sh. va tug'ilgan sanasini kiritib, testni boshlaydi.
4. Test tugagach, testni **Nofaol** qiling. Shunda boshqa hech kim kira olmaydi.
