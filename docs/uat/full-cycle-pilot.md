# UAT — دورة كاملة على الـ pilot (بعد المراحل 1-4)

الهدف: فريق الحسابات والتشغيل يمشوا دورة كاملة على الـ pilot الفاضي، **ويقروا التقارير بعد كل حركة**: شراء مواد بسيريال ← استلام بالـ Delivery Note ← Bill من الاستلام ← دفع للمورد ← عرض سعر و PI ودفعة العميل ← Job Order وتجميع المولد ← فاتورة ضريبية وتسليم.

الـ pilot اتفضّى من كل الحركات يوم 2026-11-25 (`scripts/reset_movements.py`)، فكل الأرقام بتبدأ من 1 وكل الأرصدة صفر. المراحل بالتفصيل: [Phase 1](phase1-inventory-accounting.md)، [Phase 2](phase2-receipts-bills.md)، [Phase 3](phase3-numbering-vat.md)، [Phase 4](phase4-ledgers-roles.md).

## قبل ما تبدأ
- كل خطوة بالمستخدم بتاع الـ role بتاعها: **Salesperson**، **Accountant**، **Operation Manager**، **Purchasing & Storekeeper** (واحد بيشتري وبيستلم).
- الأسعار في المثال **أرقام تجربة**، مش أسعار حقيقية. اكتبها زي ما هي علشان القيود تطلع زي الجداول تحت.
- المولد: **Cummins Diesel Generator Set 100 kVA** (`4U-C100`)، الدينامو **4U**. الـ BoM بتاعه من الكتالوج:
  - ماتور `ENG-6BT5.9-G1` (Engines، سيريال إجباري)
  - دينامو `ALT-4U-100` (Alternators، السيريال في نفس عمود Serials)
  - Canopy `CAN-C100` (Genset Bodies، سيريال إجباري)
- الـ Overhead العام **20%** (Settings ← Manufacturing ← Generator overhead).
- بعد كل خطوة فيه ✅ بالتقرير اللي تفتحوه والرقم اللي لازم يطلع. القيود كلها في Accounting ← Accounting ← **Journal Items** (فلتر بالمرجع)، وفيها عمود **Counterpart**.

## الخطوة 0: الكروت (Accountant)
- Contacts ← New: **مورد تجربة** (شركة)، البلد United Arab Emirates، TRN **`100123456700003`**.
  - ✅ جرّب الأول TRN غلط (`12345`) ← بيرفض: *must be 15 digits*. وبعد الـ TRN الصح ✅ **VAT Registered (UAE)** اتعلّمت لوحدها.
- Contacts ← New: **عميل تجربة** (شركة)، الإمارات، TRN **`100987654300003`**.
- ✅ **AQT TRADING**: الـ TRN بتاعه 7 أرقام، صلّحه لـ 15 رقم (لو مش معاك الرقم الحقيقي سيبه، بس ما تعملوش عليه فواتير).

## الخطوة 1: أمر الشراء (Purchasing)
Purchase ← Orders ← New، المورد: **مورد تجربة**:

| الصنف | الكمية | السعر |
|---|---|---|
| ENG-6BT5.9-G1 | 1 | 22,000 |
| ENG-6BT5.9-G1 | 1 | 23,000 |
| ALT-4U-100 | 1 | 7,200 |
| ALT-4U-100 | 1 | 7,600 |
| CAN-C100 | 1 | 8,800 |
| **الإجمالي** | | **68,600** + VAT 5% = **72,030** |

- Confirm (والـ Operation Manager يعمل Approve لو طلب).
- ✅ الرقم **PO001**. ✅ زرار **Print PO** ظاهر فوق ← الـ PDF بشروط الدفع.
- ✅ مفيش قيد (أمر الشراء لوحده مالوش قيد).

## الخطوة 2: الاستلام (Purchasing & Storekeeper)
Receive Products من الـ PO (أو Inventory ← Receipts ← **WH/IN/00001**):
- سيريال كل ماتور (مثلًا `ENG-T-0001` للي بـ 22,000 و `ENG-T-0002` للي بـ 23,000) وسيريال الـ Canopy (`CAN-T-0001`) وسيريالات الدينامو (`ALT-T-0001, ALT-T-0002`) كلهم في نفس عمود **Serials**.
- **Vendor Invoice No.**: `TEST-INV-001`.
- Validate من غير Delivery Note ← ✅ بيرفض: *Attach the vendor's Delivery Note*. ركّب صورة أو PDF في خانة **Delivery Note** ← Validate.

| القيد | مدين | دائن |
|---|---|---|
| WH/IN/00001 | 134004 Stock - Raw Material **68,600** | 212006 Goods Received Not Invoiced **68,600** |

- ✅ الـ Accountant: إشعار في الـ **Inbox** (Discuss) فيه رقم الاستلام، و `TEST-INV-001`، والأصناف بالسيريالات، والـ Delivery Note مرفق؛ ومهمة **Vendor bill: WH/IN/00001**.
- ✅ Inventory ← Reporting ← **Stock Valuation** = **68,600**. والدينامو في كارت المنتج Cost = **7,400** (المتوسط)، والماتور كل سيريال بسعره (Lots/Serial Numbers: 22,000 و 23,000).
- ✅ Audit Reports ← **General Ledger** ← حساب 134004: **68,600.00 Dr**، والـ Counterpart `212006 Goods Received Not Invoiced`.

## الخطوة 3: فاتورة المورد من الاستلام (Accountant)
Accounting ← Vendors ← Bills ← New: المورد، Bill Date، خانة **Receipt** ← WH/IN/00001.
- ✅ السطور اتملت لوحدها بالكميات اللي وصلت، والـ Bill Reference = `TEST-INV-001`، والـ Delivery Note في الـ chatter، والمهمة اتقفلت.
- Confirm ← ✅ الرقم **`4U-BILL-2026-0001`**.

| القيد | مدين | دائن |
|---|---|---|
| 4U-BILL-2026-0001 | 212006 GRNI **68,600** + 110003 VAT IN **3,430** | 211001 Suppliers **72,030** |

- ✅ 212006 رصيده **صفر** (الاستلام والـ Bill قفلوا بعض).
- ✅ Partner Reports ← **Vendor Ledger**: مورد تجربة **72,030.00 Cr**.
- ✅ Audit Reports ← Tax Report: ضريبة المشتريات **3,430**.

## الخطوة 4: الدفع للمورد (Accountant)
على الـ Bill ← **Pay** ← Journal: Bank ← Create Payment.

| القيد | مدين | دائن |
|---|---|---|
| PBNK1/2026/00001 | 211001 Suppliers **72,030** | 131211 Outstanding Payments **72,030** |

- ✅ الـ Bill بقى **Paid**، و Vendor Ledger: مورد تجربة **0.00**.
- 131211 بيفضل لحد ما الحركة تتطابق مع كشف البنك (Bank Reconciliation)، وساعتها بتتنقل لـ 131204 Bank.

## الخطوة 5: عرض السعر والـ PI (Salesperson)
Sales ← New: **عميل تجربة**، المولد Cummins 100 kVA (دينامو 4U)، Supply: **Assemble**.
- السعر من الكتالوج بيتحط لوحده؛ **للتجربة غيّره لـ 60,000** (+ VAT 5% = **63,000**).
- اطبع العرض ← ✅ بشكل QT 1112 (الـ letterhead، والـ datasheet، والـ Terms).
- **Create PI** ← ركّب أمر الشراء بتاع العميل وإيصال التحويل ← Send to Accountant.
- ✅ الرقم **S001**، ومفيش قيد لسه.

## الخطوة 6: دفعة العميل والتأكيد (Accountant)
أوردر البيع ← **PO Matches** ← **Register Payment** 63,000 على Bank ← **Confirm** ← الـ Job Order بيتعمل (**MO001**).

| القيد | مدين | دائن |
|---|---|---|
| دفعة العميل | 131210 Outstanding Receipts **63,000** | 133001 Customers **63,000** |

- ✅ Partner Reports ← **Customer Ledger**: عميل تجربة **63,000.00 Cr** (دفعة مقدمة لسه ما اتفوترتش).

## الخطوة 7: صرف الخامات (Operation Manager / Storekeeper)
Job Order MO001 ← تابة Serial ← **Deliver Materials**: الماتور **`ENG-T-0002`** (اللي بـ 23,000)، والدينامو، والـ Canopy `CAN-T-0001`.

## الخطوة 8: المولد خلص (Operation Manager)
Job Order ← **Finish** ← ✅ سيريال المولد = سيريال الماتور `ENG-T-0002`.

| القيد | مدين | دائن |
|---|---|---|
| صرف الخامات (MO001) | 134002 Work In Progress **39,200** (23,000 + 7,400 + 8,800) | 134004 Stock - Raw Material **39,200** |
| المولد خلص (MO001) | 134001 Stock - Finished Goods **47,040** | 134002 WIP **39,200** + 530082 Overhead Applied **7,840** (20%) |

- ✅ 134002 WIP رصيده **صفر**.
- ✅ 134004 فاضل فيه **29,400** (ماتور `ENG-T-0001` بـ 22,000 + دينامو بـ 7,400)، و Stock Valuation = 29,400 خامات + 47,040 مولد.
- ✅ مفيش ولا سطر على 421001 Cost Of Sales لسه.

## الخطوة 9: الفاتورة الضريبية والتسليم (Accountant)
أوردر البيع ← **Create Tax Invoice** ← Confirm ← ✅ الرقم **`4U-INV-2026-0001`**، وتحت اسم العميل **TRN: 100987654300003**، والـ Confirm سلّم المولد (**WH/OUT/00001**).

| القيد | مدين | دائن |
|---|---|---|
| 4U-INV-2026-0001 | 133001 Customers **63,000** | 410002 Sales Generators **60,000** + 110002 VAT OUT **3,000** |
| WH/OUT/00001 | 421001 Cost Of Sales **47,040** (عليه Analytic الـ Job Order) | 134001 Stock - Finished Goods **47,040** |

- ✅ الفاتورة **Paid** (الدفعة اتطبقت عليها لوحدها)، و Customer Ledger: عميل تجربة **0.00**.
- ✅ الفاتورة فيها الإيراد والضريبة بس، مفيش سطور تكلفة.
- ✅ على الفاتورة زرار **Delivery Notes** ← WH/OUT/00001، وعلى إذن التسليم **Tax Invoice: 4U-INV-2026-0001** وجدول **Generator Serial Numbers**.

## الأرصدة بعد كل خطوة
Audit Reports ← **Trial Balance** (أو General Ledger) بعد كل خطوة. Dr = مدين، Cr = دائن، والفاضي = صفر.

| الحساب | 2 استلام | 3 Bill | 4 دفع مورد | 6 دفعة عميل | 8 Finish | 9 فاتورة وتسليم |
|---|---|---|---|---|---|---|
| 134004 Raw Material | 68,600 Dr | 68,600 Dr | 68,600 Dr | 68,600 Dr | 29,400 Dr | 29,400 Dr |
| 134002 WIP | | | | | | |
| 134001 Finished Goods | | | | | 47,040 Dr | |
| 212006 GRNI | 68,600 Cr | | | | | |
| 110003 VAT IN | | 3,430 Dr | 3,430 Dr | 3,430 Dr | 3,430 Dr | 3,430 Dr |
| 211001 Suppliers | | 72,030 Cr | | | | |
| 131211 Outstanding Payments | | | 72,030 Cr | 72,030 Cr | 72,030 Cr | 72,030 Cr |
| 131210 Outstanding Receipts | | | | 63,000 Dr | 63,000 Dr | 63,000 Dr |
| 133001 Customers | | | | 63,000 Cr | 63,000 Cr | |
| 530082 Overhead Applied | | | | | 7,840 Cr | 7,840 Cr |
| 421001 Cost Of Sales | | | | | | 47,040 Dr |
| 410002 Sales Generators | | | | | | 60,000 Cr |
| 110002 VAT OUT | | | | | | 3,000 Cr |

## في الآخر
- ✅ **Trial Balance**: إجمالي المدين = إجمالي الدائن.
- ✅ **Profit and Loss** (Generic Statements): إيراد 60,000 − تكلفة 47,040 + Overhead Applied 7,840 = **20,800** ربح. (الـ Overhead Applied بيقفل قصاد مصاريف المصنع الحقيقية لما تتسجل.)
- ✅ **Balance Sheet**: خامات 29,400 + VAT IN 3,430 + Outstanding Receipts 63,000 − Outstanding Payments 72,030 = **23,800** = VAT OUT 3,000 + ربح السنة 20,800.
- ✅ **Job Order ← Profitability**: 60,000 − 47,040 = **12,960** (المولد بتكلفة سيريالاته + 20%).
- ✅ **Tax Report**: مبيعات 3,000 VAT OUT، ومشتريات 3,430 VAT IN، كل واحدة في سطر.
- ✅ في أي تقرير (General Ledger، Partner Ledger، Bank Book) اضغط على السطر ← بيفتح القيد نفسه.
- ✅ البحث بالسيريال `ENG-T-0002` في Receipts و Deliveries و Manufacturing Orders و Generator Cards بيلاقيه.

لو أي رقم طلع مختلف، ابعتولي صورة الـ Journal Entry والتقرير.
