# UAT — Phase 1: تقييم المخزون والتصنيع والسيريال

الهدف: فريق الحسابات يتأكد من **القيود الأربعة** في دورة واحدة: شراء 5 خامات ← تصنيع مولد واحد ← بيع مولد واحد. الشرح في [x4u_account §20](../specs/x4u_account.md).

اتجربت الدورة دي بالسكريبت على نسخة من داتابيز التدريب، بنفس المستخدمين وبنفس الزراير، والقيود طلعت زي الجدول تحت بالظبط (2026-11-24).

## قبل ما تبدأ
- على الـ **pilot**، شركة **4U Power Generation FZC**.
- المنتجات لازم تكون في فئتها الصح. أي منتج عليه **Track Inventory** في فئة All أو Saleable، Odoo هيرفض يحفظه وهيقول الفئات المسموحة:

| المنتج | الفئة (Product Category) | السيريال |
|---|---|---|
| الماتور | All / Generator Components / **Engines** | إجباري |
| الـ CKD (ماتور + دينامو على سيريال واحد) | All / Generator Components / **CKD** | إجباري |
| الـ Canopy / الشاسيه | All / Generator Components / **Genset Bodies** | إجباري |
| الدينامو | All / Generator Components / **Alternators** | في نفس عمود Serials وقت الاستلام |
| المولد | All / **Generators** | إجباري (سيريال الماتور بتاعه) |
| قطع الغيار | All / **Spare Parts** | — |

- المنتجات الـ 3 اللي اتعملت للتجربة الأولى (`ckd 100kva cummins`، و `canopy parts 100kva cummins`، و `CUMMINS READY 100KVA`) في فئة All، ودي سبب المشكلة. اعملوا المنتجات من جديد في الفئات دي (أو اسألوني أصلّح القديمة).

## المثال (المخزن فاضي، Overhead 20%)

| الخطوة | مين | فين في Odoo | اللي بيحصل |
|---|---|---|---|
| 1. شراء 5 وحدات | Purchasing | Purchase ← Orders ← New | ماتورين (22,000 و 23,000)، ودينامو اتنين (7,200 و 7,600)، و Canopy واحد (8,800) = **68,600** ← Confirm (والـ GM / Operation Manager يعمل Approve لو طلب) |
| 2. الاستلام | Storekeeper | Inventory ← Receipts ← الاستلام بتاع الـ PO | سيريال كل ماتور و Canopy ودينامو في نفس عمود **Serials** ← Validate |
| 3. فاتورة المورد | Accountant | الـ PO ← Create Bill | Bill Date ← Confirm |
| 4. عرض السعر والـ PI | Salesperson | Sales ← New: مولد 100 kVA، Supply: Assemble | Create PI ← أمر الشراء بتاع العميل وإيصال التحويل ← Send to Accountant |
| 5. الدفع والتأكيد | Accountant | أوردر البيع | PO Matches ← Register Payment ← Confirm ← الـ Job Order بيتعمل |
| 6. صرف الخامات | Storekeeper | Job Order ← **Deliver Materials** | اختار الماتور اللي بـ 23,000 والدينامو والـ Canopy بالسيريال |
| 7. التصنيع خلص | Operation Manager | Job Order ← **Finish** | سيريال المولد = سيريال الماتور |
| 8. الفاتورة والتسليم | Accountant | أوردر البيع ← **Create Tax Invoice** ← Confirm | الـ Confirm بيسلّم المولد للعميل |

## القيود اللي لازم تطلع
Accounting ← Accounting ← **Journal Items**، فلتر بالمنتج أو بالمرجع (WH/IN، MO، WH/OUT). كل سطر مخزون اسمه فيه السيريال (`... - SN ENG-0002`).

| # | المستند | مدين | دائن |
|---|---|---|---|
| 1 | **الاستلام** (WH/IN) | 134004 Stock - Raw Material **68,600** | 212006 Goods Received Not Invoiced **68,600** |
| 1b | فاتورة المورد | 212006 GRNI 68,600 + VAT In | 211001 Suppliers |
| 2 | **صرف الخامات** (MO، مع Finish) | 134002 Work In Progress **39,200** (ماتور 23,000 + دينامو 7,400 + Canopy 8,800) | 134004 Stock - Raw Material **39,200** |
| 3 | **المولد خلص** (MO) | 134001 Stock - Finished Goods **47,040** | 134002 WIP **39,200** + 530082 Overhead Applied **7,840** (20%) |
| 4 | **التسليم** (WH/OUT) | 421001 Cost Of Sales **47,040** (عليه Analytic الـ Job Order) | 134001 Stock - Finished Goods **47,040** |
| 4b | الفاتورة الضريبية | 133001 Customers | 410002 Sales Generators + 110002 VAT OUT |

## اللي تتأكدوا منه كمان
- **مفيش ولا سطر على Cost Of Sales قبل التسليم** (لا مع الاستلام ولا مع فاتورة المورد).
- **الفاتورة الضريبية** فيها الإيراد والضريبة بس، مفيش سطور تكلفة.
- **WIP (134002)** رصيده صفر بعد Finish.
- **المتوسط**: بعد الاستلام، سعر الدينامو (Cost في كارت المنتج) = **7,400** = (7,200 + 7,600) ÷ 2. الماتور كل سيريال بسعره: Inventory ← Products ← Lots/Serial Numbers ← الماتور بـ 22,000 والتاني بـ 23,000، وكارت المنتج بيعرض المتوسط 22,500.
- **المخزن بعد الدورة**: 134004 فاضل فيه **29,400** (الماتور بـ 22,000 + دينامو بـ 7,400). Inventory ← Reporting ← **Stock Valuation** لازم يقول نفس الرقم.
- **الربحية**: Job Order ← Profitability: سعر البيع − 47,040.
- **السيريال ظاهر**: عمود **Serial Numbers** في ليستة الـ Receipts والـ Deliveries، والبحث بيه (اكتب السيريال في البحث ← Serial Number)، وعمود **Generator Serial** في ليستة الـ Manufacturing Orders، وعلى الـ Delivery Slip.

لو أي رقم طلع مختلف، ابعتولي صورة الـ Journal Entry والمنتج.
