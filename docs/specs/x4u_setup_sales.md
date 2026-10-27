# Spec — إعداد المبيعات والـ Job Order لـ 4U (`x4u_setup_base` + `x4u_setup_4u`) — v0.2 DRAFT

- الحالة: **مسودة للموافقة**. مفيش كود اتكتب.
- آخر تحديث: 2026-10-20. v0.2 أضافت دورة الـ Job Order (blueprint §7) وشكل المنتج من الـ datasheets.
- DB الشغل: `odoo4u_base` (نظيفة، من غير demo).
- العلامات: ✅ متفق عليه · 🟡 قيمة افتراضية مستنية إجابتك (رقم السؤال من قائمة الـ 43، أو J من الـ blueprint §7)
- الموديول المصاحب: [`x4u_job_order`](x4u_job_order.md) (شاشة الـ Job Orders ومتابعة القطع).

---

## 1. الهدف
إعداد المبيعات والتجميع بتاع 4U يبقى **كود في الـ repo**، مش ضغطات في الشاشات. كده نقدر نعيده بالظبط على الـ staging والـ production، والجزء المشترك يتعمل مرة واحدة ويتستخدم في ATA.

## 2. الدورة اللي الإعداد ده بيخدمها
```
Quotation (موديل AQT + Open/Canopy + alternator) ← العميل يوافق ← Confirm SO
  ← Job Order (MO) أوتوماتيك، ورقمه = serial المولد
  ← 3 RFQs أوتوماتيك مربوطة بالأمر: Engine، Alternator، جسم AQT ← موافقة المدير العام ← PO
  ← الاستلام (القطع محجوزة للأمر ده بس)
  ← Material Delivered: صرف القطع للمصنع ("Pick Components")
  ← تركيب + اختبار ← المولد يدخل المخزن بالـ serial
  ← فحص الجودة ← التسليم ← Job Order Finished (والكارت ياخد العميل والضمان)
```

## 3. حالة `odoo4u_base` (اتعملت 2026-10-19)
| البند | الحالة |
|---|---|
| الموديولات | `sale_management`، `crm`، `purchase`، `stock`، `mrp` (+ `sale_mrp`)، `quality_control_mrp_oca`، `x4u_generator` |
| الشركة | "4U Power Generation (DEV)": اسم placeholder، الدولة AE، العملة AED. البيانات الحقيقية على السيرفر بس |
| Localization | `l10n_ae`: ضرايب VAT 5% لكل إمارة، و Fiscal Positions لكل إمارة + "Non-UAE" للتصدير |
| شجرة الحسابات | الإماراتية **مؤقتًا**، وهتتبدّل بالشجرة الـ custom (C21) |
| اللغات | English (واجهة الـ admin) + العربي (`ar_001`) |
| demo | مفيش |

## 4. التصميم: موديولين للإعداد (data فقط، `noupdate`) + سكريبت import
| الجزء | فيه إيه | يتثبّت على |
|---|---|---|
| `x4u_setup_base` | المشترك: Settings، وحدات القياس، أقسام المنتجات، الـ attributes (Enclosure، Alternator)، مراحل CRM، شروط الدفع | DB الـ 4U و DB الـ ATA |
| `x4u_setup_4u` | الخاص بـ 4U: الترقيم (SO، Job Order)، Manufacturing 2 steps، الـ routes، الـ Pricelists، فريق المبيعات، Quotation Template، منتجات الخدمات | DB الـ 4U بس |
| `scripts/import_generator_models.py` | بيقرا الـ Excel master من `private/` (برا الـ Git) ويعمل المنتجات والـ BOMs وبيانات الكارت | يتشغّل يدوي بعد مراجعة الـ Excel |

- الداتا `noupdate="1"`: أي تعديل من الشاشة **مش هيتمسح** مع الـ upgrade.
- الـ Settings بتتطبق بـ `res.config.settings` + `execute()` وقت التثبيت.
- **مفيش بيانات حقيقية في الكود.** الموديلات وأسعارها في `private/` بس، والسكريبت في الـ repo من غير داتا.

## 5. الإعدادات
| الإعداد | القيمة | ليه | الحالة |
|---|---|---|---|
| Units of Measure | ON | الكابلات: رول ومتر | ✅ C7 |
| Product Variants | ON | Open/Canopy × alternator (§6) | ✅ datasheets |
| Pricelists | ON (Advanced rules) | أسعار حسب العميل، و USD | ✅ س 21 |
| Discounts | ON | الخصم على السطر، وموافقته في M4 | ✅ س 21 |
| Quotation Templates | ON | عرض السعر فيه كل التفاصيل | ✅ C13 |
| Customer Addresses | ON | عنوان الفاتورة غير عنوان الموقع | افتراضي |
| Pro-forma Invoice | ON | التصدير والـ LC | افتراضي |
| Incoterms | ON | التصدير | ✅ س 3 |
| Margins | **OFF** | رؤية التكلفة لسه هتتحدد | س 41 |
| Online Signature / Payment | OFF | الموافقة دلوقتي برا السيستم | افتراضي |
| Multi-currency | USD مفعّلة جنب AED | | ✅ C2 |
| Lots & Serial Numbers | ON | serial المولد = رقم الـ Job Order | ✅ C3 |
| Manufacturing: Work Orders | OFF | 4U فيها مرحلة واحدة "تركيب + اختبار" | ✅ J5 |
| Purchase: Order Approval | ON، الحد = 0 (كل الأوامر) | المدير العام بيوافق | ✅ C10 |

## 6. المنتجات (من الـ datasheets — `private/generator-models-master.xlsx`)
### 6.1 المولد (المنتج اللي بيتباع)
| البند | القيمة | الحالة |
|---|---|---|
| المنتج | **منتج لكل موديل AQT** (مثلًا `AQT-500` Perkins 2506A-E15TAG1). الاسم: "AQT-500 — 500 kVA Standby / 455 kVA Prime — Perkins" | ✅ datasheets |
| الـ Attributes | **Enclosure**: Open / Canopy. **Alternator**: AQT / Leroy-Somer / Stamford | ✅ datasheets |
| إنشاء الـ variants | **Dynamically**: الـ variant يتعمل لما يتباع بس، فمش هيبقى عندنا ~700 variant فاضيين | ✅ |
| التتبع | Serial، والـ serial = رقم الـ Job Order | ✅ C3 / J11 |
| الـ Routes | Manufacture + MTO (أي SO بيفتح Job Order) | ✅ C4 |
| كارت المولد | `x4u_is_generator`، وبيانات الكارت من الـ Excel: Prime / Standby kVA، المحرك، الـ alternator حسب الـ variant | ✅ |
| الضمان الافتراضي | **12 شهر أو 1000 ساعة أيهما أقرب** (مكتوب في كل datasheet)، ويتعدّل من سطر البيع (M1) | ✅ س 26 |
| الأبعاد والوزن | من الـ Excel لكل نوع (Open / Canopy)، تظهر في عرض السعر | ✅ |

### 6.2 المكونات (التلاتة اللي بتتشري لكل أمر)
| المكون | المنتج | الـ Route | المورد | الحالة |
|---|---|---|---|---|
| Engine | منتج لكل موديل محرك (مثلًا "Perkins 2506A-E15TAG1") | Buy (Purchase Request) + MTO ("Take from stock, else order") | تختاره المشتريات لكل طلب | ✅ J2 / J3 |
| Alternator | منتج لكل موديل alternator (مثلًا "Stamford HCI544D") | Buy (Purchase Request) + MTO | تختاره المشتريات لكل طلب | ✅ J2 / J3 |
| جسم المولد | منتج لكل موديل + نوع (مثلًا "Genset Body — AQT-500 Canopy") | Buy (Purchase Request) + MTO | تختاره المشتريات (غالبًا AQT) | ✅ J4 |

- **موردين كتير**: الـ Job Order بيعمل **طلب مواد** لوحده (OCA `purchase_request`) مكتوب عليه رقمه، والمشتريات تختار المورد والسعر والكمية لكل سطر وتعمل منه الـ PO (`x4u_job_order` §5).
- **الأسعار** (شراء وبيع) بتتسجل في Odoo نفسه، مش في الـ Excel، وأي قائمة تتصدّر Excel من Odoo.

- **الـ BOM**: واحدة لكل موديل فيها: سطر المحرك + 3 سطور alternator (كل سطر بـ "Apply on Variants" على اختياره) + سطرين جسم (Open / Canopy). Odoo بيختار السطور الصح حسب الـ variant اللي اتباع.
- **مفيش سيريال للمحرك والـ alternator** (المخزن مش هيكتب أرقام). المولد له رقمين: رقم البيع، ورقم الـ Job Order (= serial) ✅ J10.
- **المكونات تتباع لوحدها كمان** (Can be Sold = ON) ✅ J6.

### 6.3 الأقسام ووحدات القياس
| البند | القيمة الافتراضية | الحالة |
|---|---|---|
| أقسام المنتجات | All ← **Generators**، **Generator Components** (Engines، Alternators، Genset Bodies)، Spare Parts، Services. وأقسام ATA (ATS & Panels، Solar) تتضاف مع ATA | 🟡 س 3 |
| نظام الأكواد | المولد = كود AQT (`AQT-500`، `AQT-CU-110A`، `AQT-BD-165`، `AQT-KU-22B`). المكونات والقطع مستنية أمثلة | 🟡 س 4 |
| وحدات القياس | Units، m، **Roll (91 m)**، L، kg | 🟡 س 6 |
| منتجات الخدمات | Installation، Transport، Commissioning (Service) | 🟡 س 17 |
| الضريبة على المبيعات | 5% Sharjah كـ default، والتصدير 0% بالـ Fiscal Position "Non-UAE" | 🔵 س 29 (المحاسب) |

## 7. المخزن والتجميع (`x4u_setup_4u`)
| البند | القيمة | الحالة |
|---|---|---|
| Manufacturing steps | **2 steps**: "Pick Components" (= Material Delivered) ثم المنتج النهائي | ✅ J8 |
| ترقيم الـ Job Order | **`MO001`** (مستمر من غير سنة، وده sequence الـ Manufacturing operation type). كان `4U-PO-001`، اتغير 2026-10-27 | ✅ x4u_job_order v0.4 V1 |
| ترقيم أوامر الشراء | **`PO001`**. كان `P00001`، اتغير 2026-10-27 | ✅ v0.4 V1 |
| ترقيم أوامر البيع | **`S001`**. كان `4U-SO-001`، اتغير 2026-10-27 | ✅ v0.4 V1 |
| فحص الجودة | OCA `qc.trigger` على المولد قبل التسليم، والتسليم ممنوع لحد ما يبقى passed (موجود في `x4u_generator`) | ✅ س 28 |
| أماكن المخزن | Stock، Pre-Production (القطع اللي اتصرفت للمصنع)، والمولد الجاهز يرجع Stock | ✅ |

## 8. CRM وفريق المبيعات
| البند | القيمة | الحالة |
|---|---|---|
| المراحل | New ← Quotation Sent ← Negotiation ← Won (والـ Lost بأسباب) | ✅ C12 |
| Leads | OFF: Opportunities على طول | افتراضي |
| فريق المبيعات | "4U Sales": مندوبين اتنين + مدير | ✅ س 23 |
| الصلاحيات | المندوب: "Own Documents Only". المدير: "All Documents" | ✅ C18 |
| المستخدمين على dev | test users بأسماء وهمية | rule 4 |

## 9. الأسعار وشروط الدفع وعرض السعر
| البند | القيمة الافتراضية | الحالة |
|---|---|---|
| شروط الدفع | Immediate، 100% Advance، 50% Advance / 50% Before Delivery، 30 Days، 60 Days، LC at Sight | 🟡 س 12 |
| الدفعة المقدمة | متاحة من أمر البيع | 🟡 س 13 |
| الـ Pricelists | Standard (AED)، Contractors (AED)، Distributors (AED)، Export (USD) | 🟡 س 14 |
| صلاحية عرض السعر | 30 يوم | 🟡 س 15 |
| Quotation Template "Generator Supply" | سطر المولد (موديل + نوع + alternator) + Optional Products (Installation، Transport، Commissioning) + فقرات: المواصفات، مدة التسليم، الضمان، شروط الدفع، الشروط والأحكام | 🟡 س 16، 17 |

## 10. موديولات المرحلة دي (كل واحد ليه spec لوحده)
| # | الموديول | الحالة |
|---|---|---|
| M2 (4U) | [`x4u_job_order`](x4u_job_order.md): شاشة الـ Job Orders، الحالة، ومتابعة القطع | spec مكتوب، مستني موافقتك |
| M1 | `x4u_generator` v1.1: الضمان على سطر البيع (default 12 شهر / 1000 ساعة) ويتنقل للكارت | spec بعد ده |
| M4 | `x4u_sale_discount_approval`: الخصم فوق حد معين يستنى موافقة المدير | 🟡 س 11 |
| M5 | `x4u_reports` (الجزء الأول): عرض السعر وأمر البيع بالعربي والإنجليزي | اللوجو والـ letterhead على السيرفر |

## 11. الاختبار
- **Tests للموديولين**: التثبيت على DB مؤقتة من غير demo، ونتأكد من الـ Settings، والأقسام، والـ attributes، والـ routes، والـ 2 steps، والترقيم، والـ Pricelists، والـ Template.
- **Test للسكريبت**: يستورد Excel صغير فيه بيانات تجريبية (مش الملف الحقيقي)، ونتأكد إن المنتج والـ variants والـ BOM اتعملوا صح.
- **الـ CI** بيشغّلهم أوتوماتيك.
- **مراجعة UI معاك على `odoo4u_base`**: الدورة كاملة لمولد واحد (§2).

## 12. أسئلة v0.2 (اتجاوبت 2026-10-20)
1. ~~مين مورّد المحركات والـ alternators؟~~ ← **AQT**، المورد الوحيد للتلاتة.
2. ~~الأسعار في الـ Excel ولا في Odoo؟~~ ← **في Odoo**، وكل حاجة تتصدّر Excel من Odoo.

## 13. خارج النطاق دلوقتي
المحاسبة (مستنية المحاسب)، ATA، والبيانات الحقيقية على dev.
