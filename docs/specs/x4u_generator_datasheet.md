# Spec — بيانات الـ datasheet على المولد + الـ importer — v0.3

- الحالة: **v0.3 ✅ اتنفّذت** (2026-11-24، المستخدم: "لي مش منضافه ؟" والـ pilot شغال؛ اختار: **الأسعار من الـ price lists بتاعة 2026**، **الإضافات جوه سطر المولد**، **الكتالوج الأول وبعده شكل QT 1112**، "**ما في open**"، و **Stamford = Price on request**، وخانة للإضافات بتأثر على السعر والسعر يفضل يتعدّل). اتنفّذت في `x4u_generator` 18.0.1.1.0 و `x4u_job_order` 18.0.1.17.0 و `scripts/fetch_datasheets.py`، `scripts/generator_catalog.py`، `scripts/import_generators.py`. شكل QT 1112 (Options A / B / C وملخص الأسعار) هو الخطوة الجاية ([x4u_reports](x4u_reports.md)).
- v0.2 ⏸ (2026-11-13): كانت موقوفة لحد ما الموقع يخلص.

## 0b. v0.3 (2026-11-24) ✅
| # | القاعدة |
|---|---|
| V1 | **المصدر**: صفحات الموقع (JSON-LD لكل موديل)، وهي نفس الـ datasheets اللي على الدرايف (4U-DS-xxx، الموقع هو اللي بيطلعها). 156 موديل: Cummins 41، Perkins 41، Lister Petter 39، Baudouin 26، Kubota 9. الملفات في `private/datasheets/` (برا Git) |
| V2 | **Silent canopy بس** (مفيش open). الـ variant = الـ Alternator: **4U** (صفوف KWISE / CHINA / LP في الـ price list)، **Leroy-Somer** (صفوف TAL)، **Stamford** (لو له frame في الـ datasheet) |
| V3 | **الأسعار** من `UAE_PRICE_LIST_2026` و `EXPORT_PRICE_LIST_2026` (الدرايف): **Standard** = الإمارات، **Export (AED)** = التصدير زي QT 1112، و **Export** (USD) بيتبع Export (AED) بالربط. Perkins بالإسترليني في قايمتين GBP، وبيدخل الدرهم بسعر اليوم، متقرّب لقرشين. الصف بيتلاقى بالمحرك (Baudouin: المحرك + الـ frame) |
| V4 | **Price on request**: Stamford، و 37 موديل مالهمش صف في قوايم 2026 (أغلب سلسلة L، و Perkins الكبيرة 4012 / 4016، و C26، و B820...). السطر بيطلع **"As requested"**، والـ PI مابيطلعش غير لما السعر يتكتب |
| V5 | **سطر عرض السعر**: الوصف بيتكتب لوحده من الـ datasheet زي QT 1112 (المحرك، والـ alternator بالـ frame بتاعه، والكنترولر، والـ breaker، والتانك، والكانوبي). عمود **Extras** (نص بيتكتب في آخر الوصف) و **Extras Price** (بيتزوّد على السعر)، والسعر يتعدّل باليد، والخصم في عمود Disc.% |
| V6 | **المكونات والـ BoM** لكل موديل: المحرك (Engines، بالسيريال، مشترك بين الموديلات)، والـ alternator لكل اختيار (Alternators)، والـ Silent Canopy (Genset Bodies، المورد AQT لو موجود)، عشان الـ Job Order يشتغل. BoM معمولة باليد مابتتلمسش |
| V7 | **الـ importer بيتعاد** في أي وقت (لما الـ price list أو الموقع يتغير): الموديل بكوده، وبيحدّث البيانات والأسعار، ومابيمسحش حاجة |

| # | الاختبار (`x4u_job_order/tests/test_generator_catalog.py`) |
|---|---|
| T1 / T7 | موديل بالـ 3 alternators والكود والـ datasheet والـ BoM، والاختيار اسمه "4U" |
| T2 | الأسعار: UAE و Export (AED) و Export (USD) بالربط، و Perkins من GBP بسعر اليوم، و Stamford من غير سعر |
| T3 | استيراد تاني بيحدّث الموديل والـ datasheet والسعر من غير تكرار |
| T4 | زي QT 1112: سعر القايمة + Extras 3,300 (أرقام تجريبية في الـ test، الأسعار الحقيقية في private/ بس)، والوصف فيه المحرك والـ frame والإضافات، والسعر المكتوب باليد بيفضل |
| T5 | Stamford: "As requested"، والـ PI بيترفض لحد ما السعر يتكتب |

## 9. عرض السعر بشكل QT 1112 (v0.4، 2026-11-25) ✅
المستخدم: "Yes, start it" (الخطوة اللي بعد الكتالوج). اتنفّذت في `x4u_job_order` 18.0.1.18.0.

| # | القاعدة |
|---|---|
| Q1 | **طباعة "Quotation (4U)"** (Print، وهي اللي بتروح بالإيميل): الـ letterhead فوق كل صفحة وشريط الماركات تحت، و Quotation No. / Date / Valid for، وكارتين Prepared for (العميل، Attention، العنوان، Your Ref.) و Prepared by (الشركة، المندوب، الإيميل، الـ TRN)، ومربع **Requirement** الأصفر، والجدول، ومربع **Delivery**، و **Price Summary**، وصفحة **Terms & Conditions** من شروط العرض. كل بند بيفضل في صفحة واحدة |
| Q2 | **Quote as Options** (تاب Quotation (4U) في العرض): كل مولد = Option A / B / C، عليه **Recommended** أو **Alternative**، وعنوان (لوحده: الماركة + الدينامو، أو اكتبه في Option Title). كل Option ليه إجمالي لوحده في Price Summary ("Each option is a separate total")، والسطور التانية (خدمات) بتتزوّد على كل Option |
| Q3 | **Choose**: لما العميل يختار، المندوب يدوس Choose على السطر ده، والـ Options التانية بتتشال وبيتكتب ده في الـ chatter. الـ PI ومرور العرض للمحاسب مش بيحصلوا وفيه أكتر من Option |
| Q4 | **الـ letterhead**: صورتين على الشركة (Settings ← Companies ← 4U Letterhead)، اتاخدوا من QT 1112 نفسه، في `private/branding/` (برا Git) وبيترفعوا بـ `scripts/set_letterhead.py`. من غيرهم بيطبع اسم الشركة واللوجو |

| # | الاختبار |
|---|---|
| T8 | عرض فيه Optionين: A و B، والعنوان، و "EACH OPTION IS A SEPARATE TOTAL" في الطباعة، والـ PI بيترفض، والإيميل بيبعت Quotation (4U)، و Choose بيسيب Option واحد |
- المرجع: [docs/modules/01-sales.md](../modules/01-sales.md) (D5، D8) و [x4u_setup_sales.md](x4u_setup_sales.md) §6، و [x4u_job_order v0.8](x4u_job_order.md) (المحرك بالسيريال، والـ alternator اختياري).
- يتعمل فين: **`x4u_generator` v1.1** (المولد نفسه)، و `scripts/` (السحب من الموقع والاستيراد).
- العلامات: ✅ متفق عليه · 🟡 اقتراح مستني موافقتك

---

## 0. القرارات (2026-11-13) ✅
| # | القرار |
|---|---|
| Q1 | **المصدر = الموقع** `4ugenerators.com` (الـ datasheets الجديدة بأكواد 4U)، مش الـ Excel الماستر بتاع AQT. والـ Excel بيفضل مرجع قديم بس |
| Q2 | اختيار الـ Alternator **"AQT" ← "4U"** (4U · Leroy-Somer · Stamford)، زي الـ datasheet الجديد |
| Q3 | المورد الافتراضي للـ Canopy / Base Frame = **AQT**، والمشتريات تقدر تغيّره. المحرك والـ alternator من غير مورد ثابت |
| Q4 | **مدة التسليم مرنة**: مفيش رقم ثابت لكل موديل، لأنها على حسب جدول التشغيل في المصنع. المندوب بيحط **Delivery Date** على كل عرض سعر، والـ Job Order بياخد ميعاده منها (موجود). وده بيلغي الـ 42 يوم (D8) |

## 1. الهدف
كل موديل مولد في Odoo عليه **كل بيانات الـ datasheet** زي صفحة الموقع بالظبط. عرض السعر بيطبعها لوحده للموديل والـ variant اللي اتباع (`x4u_reports`)، والتأكيد بيفتح الـ Job Order بالمكونات الصح (BOM): المحرك بسيرياله، والـ alternator، والـ Canopy.

## 2. اللي على الموقع (اتشاف 2026-11-13)
- **160 موديل**: B = Baudouin، C = Cummins، K = Kubota، P = Perkins، و **L** (سلسلة جديدة، والماركة بتتقري من الـ datasheet نفسه).
- كل datasheet ليه رقم وتاريخ إصدار، مثلًا `4U-DS-C300 · 2026-11-09`.
- **الأكواد بتتغير**: `4U-C350` بقى **`4U-C300`** (300 / 330 kVA)، و `4U-B165` مش موجود، و `4U-K22` بقى `4U-K22-5`. علشان كده الـ importer لازم يعرف يتعامل مع موديل اختفى أو اتغير اسمه (§6).
- أقسام الـ datasheet: الأرقام الأساسية، Overview والضمان، Supply options، Key features، Output ratings على 50 Hz وعلى 60 Hz (kVA، kW، التيار)، Other voltages، Engine (Make / model، Cylinders / cycle، Aspiration، Speed، Cooling، Governing، Displacement، Bore × stroke، Charging alternator، Flywheel، Starting voltage، Fuel system، Fuel filter)، الـ Alternator لكل ماركة، Fuel consumption، الأبعاد والوزن لـ Open و Silent، Noise، و Control & protection، والملاحظات (PRP / ESP، والـ 60 Hz).

## 3. البيانات على الموديل
| النوع | إيه | ليه |
|---|---|---|
| **حقول أساسية** | الكود (Internal Reference، مثلًا `4U-C300`)، السلسلة والماركة، Prime / Standby kVA و kW على 50 Hz وعلى 60 Hz، المحرك (Make / model)، الـ Controller، الاستهلاك عند 75% prime (L/h)، الـ Noise للـ Silent، أبعاد ووزن وتانك الـ Open والـ Canopy، الضمان (شهور / ساعات)، رقم الـ datasheet وتاريخه، ولينكه | البحث والفلترة، وكارت المولد، والـ BOM |
| **كل سطور الـ datasheet** | جدول "Datasheet" على المنتج: القسم، والبند، والقيمة، بنفس الترتيب اللي على الموقع | عرض السعر بيطبعه زي الموقع بالظبط، ولو الموقع زوّد بند بيظهر لوحده من غير كود جديد |
| **الصورة** | صورة الموديل من الموقع | المنتج وعرض السعر |

- الـ **variant** اللي اتباع بياخد من البيانات دي: Open ← أبعاد Open، Canopy ← أبعاد Silent، والـ Alternator ← الـ frame بتاع الماركة دي بس.
- الـ importer بيكتب البيانات دي كلها من جديد في كل مرة، والـ **السعر لأ** (§5).

## 4. المكونات والـ BOM (لكل موديل)
| السطر | المنتج | الـ category والتتبع | بيتشري من | الـ variant |
|---|---|---|---|---|
| Engine | منتج لكل موديل محرك، مثلًا "Cummins 6LTAA9.5-G1"، ومشترك بين الموديلات اللي عليها نفس المحرك | **Engines**: بالسيريال وبقيمة كل سيريال (v0.8، أوتوماتيك) | المشتريات تختار | كل الـ variants |
| Alternator | منتج لكل frame، مثلًا "Leroy-Somer TAL-A46-F"، "Stamford …"، "4U …" | **Alternators**: سيريال اختياري (v0.8.1) | المشتريات تختار | حسب الماركة |
| Canopy / Body | "Silent Canopy — 4U-C300" و "Open Base Frame — 4U-C300" | **Genset Bodies** | **AQT** ✅ | حسب الـ Enclosure |

- المكونات عليها "Purchase Request" ✓ والـ routes بتاعة الـ Job Order (Buy + MTO)، زي النهارده.
- لو الـ datasheet مافيهوش frame لماركة معينة، الـ variant ده **مش بيتعرض للبيع**، وبيتكتب في التقرير.

## 5. السعر ومدة التسليم
- **السعر يدوي** (D2): الإدارة بتحطه على كل variant. الـ importer مايلمسش الأسعار أبدًا.
- **مدة التسليم مرنة** ✅ (Q4): مفيش رقم افتراضي على المنتج. الـ Delivery Date بيتكتب على عرض السعر حسب جدول المصنع.
  - 🟡 بعدين (مش في الـ spec دي): شاشة لجدول المصنع تقترح أقرب ميعاد.

## 6. الـ importer: خطوتين
| الخطوة | بتعمل إيه |
|---|---|
| **1. Fetch** (من الموقع) | بيقرا قايمة الموديلات وكل datasheet، وبيحفظهم **JSON** في `private/datasheets/` (برا الـ Git). وبيطلع تقرير: الجديد، واللي اتغير من آخر مرة، واللي اختفى من الموقع، والناقص في كل datasheet |
| **2. Import** (لـ Odoo) | `.\scripts\import-generators.ps1 -Database odoo4u_base [-Models 4U-C300,...]`: بيعمل أو يحدّث الموديل بالكود، والـ attributes، والبيانات، ومنتجات المكونات، والـ BOM |

- الخطوتين منفصلين: الاستيراد مش محتاج الموقع شغال، وانت تقدر تشوف الـ JSON قبل ما يدخل.
- **يتعاد** في أي وقت. مايلمسش الأسعار، ولا يمسح حاجة. والموديل اللي **اختفى من الموقع** (زي C350 ← C300) بيتكتب في التقرير، وانت اللي تقرر تعمله Archive.
- **الأول 5 samples** (واحد من كل ماركة) نراجعهم سوا في Odoo وفي عرض سعر، وبعدها الـ 160: 🟡 `4U-C300` (Cummins)، `4U-P500` (Perkins)، `4U-B150` (Baudouin)، `4U-K20` (Kubota)، `4U-L100` (السلسلة L).

## 7. "AQT" ← "4U"
- قيمة الـ Alternator في الـ attribute بتتغير لـ **4U** (نفس الـ record، فالـ variants والأوردرات القديمة مش بتتأثر).
- ماركة الـ alternator "4U" بتتعمل لكارت المولد.

## 8. Tests
| # | الاختبار |
|---|---|
| T1 | استيراد JSON تجريبي ← موديل بالـ variants والـ BOM والبيانات وسطور الـ datasheet |
| T2 | variant "Canopy + Stamford" ← الـ BOM فيها المحرك + Stamford frame + Silent Canopy، والأبعاد أبعاد الـ Silent |
| T3 | استيراد تاني بعد ما الـ kVA اتغير ← الموديل يتحدّث، وسطور الـ datasheet تتبدّل، والسعر مايتغيرش |
| T4 | تأكيد بيع ← الـ Job Order يطلب المحرك (بالسيريال) والـ frame والـ Canopy الصح، والـ Canopy مقترح من AQT |
| T5 | موديل مافيهوش frame لماركة ← الـ variant ده مش بيتعرض |
| T6 | موديل اختفى من الـ JSON ← في التقرير، ومااتمسحش |
| T7 | اختيار الـ Alternator اسمه "4U" |

## 9. أسئلة
1. 🟡 عندك **ملف بيانات الموقع** نفسه (المشروع اللي الموقع متبني منه)؟ لو آه، الـ Fetch يقرا منه بدل الصفحات، وده أضمن. لو لأ، يقرا الصفحات.
2. 🟡 الـ 5 samples في §6 مناسبين؟
