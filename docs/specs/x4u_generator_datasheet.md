# Spec — بيانات الـ datasheet على المولد + الـ importer — v0.1 DRAFT

- الحالة: **مسودة للمراجعة**. مفيش كود قبل موافقتك.
- المرجع: [docs/modules/01-sales.md](../modules/01-sales.md) (D5، D8) و [x4u_setup_sales.md](x4u_setup_sales.md) §6.
- يتعمل فين: **`x4u_generator` v1.1** (المولد نفسه)، و `scripts/import_generator_models.py`.
- العلامات: ✅ متفق عليه · 🟡 اقتراح مستني موافقتك

---

## 1. الهدف
كل موديل مولد في Odoo عليه **كل بيانات الـ datasheet** بنفس أقسام datasheet الموقع (`4ugenerators.com/en/models/<code>/datasheet`). عرض السعر بيطبعها لوحده للموديل والـ variant اللي اتباع (`x4u_reports`)، والتأكيد بيفتح الـ Job Order بالمكونات الصح (BOM).

## 2. البيانات على الموديل (تاب "Datasheet" على المنتج)
| القسم | الحقول | موجود دلوقتي؟ |
|---|---|---|
| الكود والسلسلة | `4U-C350`، Diesel generator، الماركة، 50 Hz | الكود = Internal Reference |
| Output ratings | Standby kVA/kW، Prime kVA/kW، Prime 60 Hz kVA/kW، الجهد/التردد/السرعة، Power factor، Other voltages | kVA بس |
| Engine | Make/model، Cylinders، Displacement، Bore × stroke، Aspiration، Governing، Cooling، Coolant capacity، Lube oil capacity | الماركة والموديل بس |
| Alternator | الماركات المتاحة، frame لكل ماركة (Leroy-Somer، Stamford، 4U)، Type، Insulation / protection، Voltage regulation | الماركة والموديل بس |
| Fuel consumption | 50% / 75% / 100% prime، Standby (L/h) | ❌ |
| Dimensions & weight | Open: L×W×H + الوزن. Canopy: L×W×H + الوزن. Base fuel tank، Noise @ 7 m | ❌ |
| Control & protection | Controller، Main breaker، Shutdowns & alarms | ❌ |
| الضمان | شهور / ساعات (موجودين)، والنص | ✅ |
| Notes | نص حر (PRP / ESP / Options / "Specifications are typical") | ❌ |
| الصورة | صورة الموديل | صورة المنتج العادية |
| المصدر | رابط الـ datasheet + تاريخ الإصدار (Issued) | ❌ |

- **الـ variant اللي اتباع** بيختار من البيانات دي: Open ← أبعاد Open، Canopy ← أبعاد Canopy، والـ Alternator ← الـ frame بتاع الماركة دي بس.
- 🟡 قيمة الـ Alternator "AQT" في الـ attribute: الـ datasheet الجديد بيكتب **"4U"**. نغيّرها لـ "4U"؟

## 3. المكونات والـ BOM (لكل موديل)
| السطر | المنتج | بيتشري من | الـ variant |
|---|---|---|---|
| Engine | منتج لكل موديل محرك، مثلًا "Cummins 6LTAA9.5-G1" | المورد اللي المشتريات تختاره | كل الـ variants |
| Alternator | منتج لكل frame، مثلًا "Leroy-Somer TAL-A46-F"، "Stamford HCI444D/S4L1DD41" | المشتريات تختار | حسب الماركة |
| Canopy / Body | منتج لكل موديل ونوع، مثلًا "Silent Canopy — 4U-C350" و "Open Base Frame — 4U-C350" | **AQT** (المورد الافتراضي، والمشتريات تقدر تغيّر) | حسب الـ Enclosure |

- التأكيد بيحجز من المخزن لو موجود، والناقص بيتطلب (اتعمل في `x4u_job_order`).
- 🟡 المورد الافتراضي للـ Canopy = AQT. والمحرك والـ alternator من غير مورد افتراضي.

## 4. السعر ومدة التسليم
- **السعر يدوي** (D2): الإدارة بتحطه على كل variant. الـ importer مايلمسش الأسعار أبدًا.
- **مدة التسليم** (D8): افتراضي **42 يوم** (6 أسابيع) لكل موديل، وتتعدّل من المنتج أو من عرض السعر. 🟡 الرقم.

## 5. الـ importer (`scripts/import_generator_models.py`)
| البند | التصميم |
|---|---|
| المصدر | ملف JSON في `private/datasheets/` (برا الـ Git)، فيه موديل في كل سجل بنفس أقسام §2 |
| الـ samples دلوقتي | **4U-C350** (Cummins)، **4U-P500** (Perkins)، **4U-B165** (Baudouin)، **4U-K22** (Kubota): بتتاخد من صفحات الموقع، والصور من فولدر "generators pictures" على الـ Drive |
| يتعاد | آه: يحدّث الموديل بالكود لو موجود، ويعمل الناقص. **مايلمسش** الأسعار ولا أي variant اتباع |
| بيعمل | المنتج + الـ attributes + بيانات الـ datasheet + منتجات المكونات + الـ BOM + مدة التسليم |
| تقرير | في الآخر: كام موديل اتعمل، كام اتحدّث، وإيه الناقص في كل datasheet |
| التشغيل | `.\scripts\import-generators.ps1 -Database odoo4u_base` |

## 6. الاختبار
1. استيراد الـ 4 samples ← 4 موديلات، كل واحد بـ 6 variants ممكنة (Open/Canopy × 3 alternators) وBOM صح.
2. variant "Canopy + Stamford" ← الـ BOM فيها المحرك + Stamford frame + Silent Canopy، والأبعاد أبعاد الـ Canopy.
3. تشغيل الاستيراد تاني بعد تعديل الـ kVA ← الموديل يتحدّث، والسعر مايتغيرش.
4. تأكيد بيع ← الـ Job Order يطلب المكونات الـ 3 الصح.

## 7. أسئلة
1. **مصدر الداتا على المدى الطويل**: الموقع شغال من ملف بيانات (JSON / Excel / CMS)؟ لو آه، الـ importer يقرأ منه على طول، ومحدش يكتب الداتا مرتين.
2. "AQT" ← "4U" في اختيار الـ Alternator؟
3. المورد الافتراضي للـ Canopy هو AQT؟
4. مدة التسليم الافتراضية 42 يوم؟
