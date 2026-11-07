# Spec — `x4u_account`: قوايم الحسابات، الـ PDC، حقوق الملكية، Receivables & Payables، والتسوية التلقائية — v0.2

- الحالة: **اتوافق عليها 2026-11-07** (طلب المستخدم، واختار "Full PDC cycle"). اتنفّذت في `x4u_account` 18.0.1.0.0، و `x4u_sale` 18.0.2.1.1، و `x4u_purchase` 18.0.1.0.1.
- v0.2 (2026-11-07): الطلب التاني (Journal Items، Petty Cash، الـ Capital، Payments + Due List، التسوية التلقائية، Receivable & Payable) ← §1 (1b، 2b)، §2 P8، §3، §4، §5. المستخدم اختار الاقتراح في الأربع أسئلة. اتنفّذت في `x4u_account` 18.0.1.1.0.
- المرجع: [docs/modules/06-accounting.md](../modules/06-accounting.md).
- العلامات: ✅ متفق عليه · 🟡 مستني قرارك · 🔵 مستني المحاسب

## 1. القوايم (Accounting)
| # | الطلب | التنفيذ | الحالة |
|---|---|---|---|
| 1 | الـ Assets جوه الـ Accounting | قايمة **Assets** (Assets، Compute Assets) بقت جوه **Accounting › Accounting** بعد "Payments and due list". إعداداتها (Asset Profiles، Groups) وتقاريرها فضلوا مكانهم | ✅ |
| 2 | مفيش Products في Customers و Vendors | القايمتين اتقفلوا (مش اتمسحوا). المنتجات موجودة في Sales و Purchase و Inventory | ✅ |
| 3 | Customers › Sales Orders ← **Sales Section** | اسم القايمة بس (`x4u_sale`). المحتوى زي ما هو: الـ SOs المتأكدة | ✅ |
| 4 | Vendors › Bills ← **Invoices** | اسم القايمة بس، زي Customers › Invoices. المستند نفسه لسه اسمه Vendor Bill في Odoo | ✅ |
| 5 | Vendors › Purchase Orders ← **DR** (Debit) | اسم القايمة بس (`x4u_purchase`). المحتوى زي ما هو: الـ POs وحالة الـ PI والدفع | ✅ |
| 6 | Vendors › **PDC Cheques** | §2 | ✅ |
| 1b | **Journal Items** | للـ Chief Accountant بس (Accounting Manager: أدوار Accountant و General Manager و Administrator). الباقي يستخدم Journal Entries والـ General Ledger | ✅ |
| 2b | Cash Registers ← **Petty Cash** | القايمة، والـ Cash journal، وحسابه بقوا اسمهم Petty Cash | ✅ |
| 4/6 | **Receivables & Payables** | قايمة جديدة بين Vendors و Accounting: Customer Due List، Vendor Due List (بأيام التأخير)، Customer Balances، Vendor Balances، Payments and Due List (اتنقلت هنا)، Aged Partner Balance، Open Items | ✅ §5 |

- لو الموديول اتشال (uninstall)، قوايم Odoo بترجع زي ما كانت.

## 2. الـ PDC (شيكات آجلة للموردين)
الدورة:
```
فاتورة المورد ← Register Payment ← Payment Method: PDC Cheque ← رقم الشيك + تاريخ الشيك
   القيد:  مدين  المورد (Payable)              ×
           دائن  Post Dated Cheques Issued     ×      ← الشيك "Issued"، والفاتورة "Paid" (Odoo Community مالوش "In Payment")
   ↓ في تاريخ الشيك البنك بيصرفه
كشف البنك ← Reconcile مع سطر الـ PDC
           مدين  Post Dated Cheques Issued     ×
           دائن  البنك                          ×      ← الشيك "Cleared"، والفاتورة "Paid"
   أو البنك رفضه ← زرار "Cheque Bounced" + السبب
           القيد بيتلغي، والفاتورة ترجع "Not Paid"، والسبب بيتكتب على الدفعة والفاتورة ← الشيك "Bounced"
```

| # | القاعدة | الحالة |
|---|---|---|
| P1 | Payment Method جديد **PDC Cheque** على كل Bank journal، للدفع للموردين بس | ✅ |
| P2 | حساب **Post Dated Cheques Issued** (`201020`، Current Liabilities، Reconcile) بيتعمل لوحده لكل شركة. الشيك بيستنى فيه بدل Outstanding Payments | ✅ (الكود 🔵 مع المحاسب، زي باقي الشجرة) |
| P3 | **رقم الشيك** و **تاريخ الشيك** لازم قبل الـ Confirm، في Register Payment وفي الدفعة نفسها | ✅ |
| P4 | نفس رقم الشيك مايتكررش على نفس البنك، إلا لو الأول Bounced | ✅ |
| P5 | **Cleared** = سطر الـ PDC اتطابق (Reconcile) مع كشف البنك. Odoo نفسه بيكتب على الدفعة "Paid" بدري، فالحالة دي لوحدها ("Cheque Status") | ✅ |
| P6 | **Cheque Bounced** للشيك الـ Issued بس (مش الـ Cleared)، بسبب | ✅ |
| P7 | قايمة **Vendors › PDC Cheques**: تاريخ الشيك، الرقم، المورد، البنك، المبلغ، الحالة. فلاتر: Issued، Cheque Date Passed، Due in 7 Days، Cleared، Bounced. Group by الحالة أو المورد أو الشهر | ✅ |

| P8 | الفاتورة اللي اتدفعت بشيك PDC لسه ماتصرفش بتبقى **In Payment** مش Paid، ولما الشيك يتصرف بتبقى Paid. ده للـ PDC بس، وباقي الدفعات زي Odoo Community | ✅ |
| P9 | رقم الشيك بيتكتب في وصف القيد ("PDC Cheque - Cheque 000123")، علشان كشف البنك يلاقيه لوحده (§4 R1) | ✅ |

## 3. حقوق الملكية (Capital، Share، Profit)
الشجرة كان فيها حساب واحد بس: `999999 Undistributed Profits/Losses`. اتضاف على شكل شجرة Focus (Capital In Paid، Partner Paid، Reserves & Surplus، Profit/Loss):

| الكود | الحساب | النوع |
|---|---|---|
| 301001 | Share Capital | Equity |
| 302001 | Partners' Current Accounts | Equity |
| 303001 | Statutory Reserve | Equity |
| 304001 | Retained Earnings | Equity |
| 305001 | Dividends / Profit Distribution | Equity |
| 999999 | Undistributed Profits/Losses (ربح السنة الحالية، من Odoo) | Current Year Earnings |

- 🔵 الأكواد والاحتياطي القانوني مع المحاسب (شركة Free Zone ممكن ماتحتاجش Statutory Reserve).
- 🔵 لو الشركاء محتاجين حساب جاري لكل شريك، يتعمل حساب فرعي لكل واحد تحت 302.

## 4. التسوية التلقائية ("Safe automatic")
| # | القاعدة | الحالة |
|---|---|---|
| R1 | **كشف البنك**: سطر الكشف بيتسوّى لوحده لما يكون فيه **Perfect Match**: نفس الشريك، ونفس المبلغ بالظبط، ورقم/مرجع موجود في الوصف (OCA `account_reconcile_oca`، موديل "Invoices/Bills Perfect Match"). ده بيشمل شيكات الـ PDC لما البنك يصرفها | ✅ |
| R2 | **كل ليلة 2 الصبح**: الدفعة بتتسوّى مع الفاتورة لما يكون **نفس الشريك ونفس المرجع** (Memo = رقم الفاتورة)، والمبالغ تقفل على صفر من غير Write-off (OCA `account_mass_reconcile`، طريقة "Advanced. Partner and Ref."). على حساب العملاء وحساب الموردين | ✅ |
| R3 | أي حاجة مش أكيدة (مبلغ بس من غير مرجع، فرق مبلغ) **بتفضل للمحاسب** في Reconcile | ✅ |

## 5. Receivables & Payables
- **Customer / Vendor Due List**: كل فاتورة مفتوحة ودفعة مش متسوّية، بتاريخ الاستحقاق وأيام التأخير (OCA `account_due_list` + `account_due_list_days_overdue`)، و Pivot و Graph.
- **Customer / Vendor Balances**: رصيد كل شريك. تختار الشركاء ← **Action › Partner Outstanding Statement** أو **Activity Statement** (OCA `partner_statement`، اتفعّل في Settings).
- **Payments and Due List**: زي ما كانت، اتنقلت هنا.
- **Aged Partner Balance** و **Open Items**: تقارير OCA `account_financial_report` (موجودين كمان في Reporting).

## 6. خارج النطاق
- الشيكات الآجلة **من العملاء**: OCA `account_check_deposit` (Customers › Checks Deposits) وحساب `102013 Post Dated Cheques Received`.
- طباعة الشيك نفسه.
- تذكير (to-do) قبل تاريخ الشيك: ممكن نضيفه بعدين.

## 7. الاختبار (`x4u_account/tests`)
1. القوايم: Assets جوه Accounting، و Products مقفولة، و Bills اسمها Invoices، و PDC Cheques تحت Vendors.
2. فاتورة 1,000 ← PDC ← Issued، والحساب 201020، والفاتورة In Payment، ورقم الشيك في وصف القيد ← Reconcile ← Cleared والفاتورة Paid ← Bounce ممنوع.
3. Bounce ← الدفعة Canceled، والفاتورة Not Paid، والسبب متسجل، ونفس الرقم يتكتب تاني.
4. من غير رقم أو تاريخ ← رسالة. رقم مكرر ← رسالة.
5. Manual Payment زي ما هو.
6. v0.2: Journal Items للـ Accounting Manager، و Petty Cash، و Receivables & Payables فيها 7 قوايم، وحسابات الـ Equity الخمسة، و Statements مفعّلة.
7. R1: سطر كشف بنك "Cheque 000126" بنفس المبلغ والمورد ← الشيك Cleared والفاتورة Paid لوحدهم.
8. R2: فاتورتين بنفس المبلغ ← دفعة بـ Memo = رقم الأولى ← اتسوّت. ودفعة من غير مرجع ← التانية فضلت Not Paid.
9. v0.3: شركة بالدرهم ← 100 USD = 367.25 AED، وسعر واحد بس حتى لو الإعداد اتعمل مرتين. تصحيح الأنواع والاسم. فئة الخدمات ← 500008، وفئة المصروفات ← 400050، واختيار المحاسب مابيتغيرش في الـ upgrade.

## 8. المرحلة 1: مكاسب سريعة (v0.3، 2026-11-07)
المستخدم اختار "Phase 1: quick wins" من مراجعة الحسابات. اتنفّذت في `x4u_account` 18.0.1.2.0.

| # | التعديل | الحالة |
|---|---|---|
| Q1 | **سعر الدولار**: الدرهم مربوط بالدولار عند **3.6725** (المصرف المركزي، من 1997). سعر واحد من 1997-11-01، فأي تاريخ بيتحسب صح. لو حد حط أسعار بنفسه، مابيتغيرش | ✅ |
| Q2 | **أنواع حسابات غلط في `l10n_ae`**: `100103 VAT Receivable` و `202003 VAT Payable` (حسابات تسوية الضريبة مع الـ FTA، مش عميل أو مورد) بقوا Current، و `106009 Acc. Depreciation of Motor Vehicles` بقى Fixed Asset. و `106005` اسمه بقى "Work In Progress". التعديل بيتعمل بس لو الحساب مالوش قيود | ✅ |
| Q3 | **إيراد وتكلفة لكل فئة**: المولدات 500001 / 400001، والمكونات وقطع الغيار **500015 Spare Parts Sales** (جديد) / 400001، والخدمات **500008 Service Income** / 400001، والمصروفات **400050 Others - Office Various Expenses** (مصروف تشغيل مش تكلفة مبيعات). بيتطبق بس لو الفئة لسه على الافتراضي، علشان اختيار المحاسب يفضل | ✅ (🔵 الأكواد مع المحاسب) |
| Q4 | **حساب البنك (IBAN)** على الشركة والـ Bank journal | ⏳ بيانات الشركة: بتتدخل في الداتابيز بس، مش في Git |
| Q5 | **Credit Limit** لكل عميل | ⏳ المبالغ من الإدارة |

## 9. المرحلة 2: المخزون الدائم والتكلفة (v0.4، 2026-11-07)
المستخدم وافق على التصميم واختار الاقتراح في السؤالين (الـ Overhead لحساب لوحده، وتحويل المخزون الموجود ضد 400001). اتنفّذت في `x4u_account` 18.0.1.3.0. ده بيقفل قرار **A1** في [06-accounting.md](../modules/06-accounting.md) (كان Manual Periodic).

- **التقييم**: Automated (Perpetual) + **Anglo-Saxon**، بـ FIFO، على فئات المكونات والمولدات وقطع الغيار. الخدمات والمصروفات زي ما هي.
- **ملاحظة**: `106xxx` هي مجموعة الأصول الثابتة (و `106005 Work In Progress` = أصول تحت الإنشاء)، فاتصلّح نوعها كلها (Fixed Asset)، والـ WIP بتاع التصنيع بقى حساب لوحده في `103xxx` (مجموعة المخزون والشحنات).

| الكود | الحساب | الاستخدام |
|---|---|---|
| 103001 | Inventory - Generator Components | المحركات، والـ Alternators، والـ Bodies |
| 103002 | Inventory - Finished Generators | المولدات الجاهزة |
| 103003 | Inventory - Spare Parts | قطع الغيار |
| 103004 | Work In Progress - Production | التصنيع (بيقفل على صفر مع كل MO) |
| 103005 | Goods Delivered Not Invoiced | اتسلّم ولسه مااتفوترش (Reconcile) |
| 201021 | Goods Received Not Invoiced | اتستلم ولسه فاتورة المورد ماجتش (Reconcile) |
| 400072 | Applied Manufacturing Overhead | دائن: الـ 20% اللي اتحمّلت على المولدات، قصاد المصروفات الحقيقية |
| 400036 | Write Off Inventory (موجود) | فروق الجرد والـ Scrap |

القيود:
```
استلام من المورد       مدين 103001 Inventory          / دائن 201021 GRNI
فاتورة المورد          مدين 201021 GRNI + 104041 VAT   / دائن 201002 Payables
صرف المكونات للـ MO     مدين 103004 WIP                / دائن 103001
المولد خلص (+20%)      مدين 103002 (القطع + 20%)       / دائن 103004 (القطع) + 400072 (الـ 20%)
تسليم للعميل           مدين 103005 GDNI               / دائن 103002
فاتورة العميل          مدين 102011 / دائن 500001 + 201017 VAT
                       مدين 400001 COGS               / دائن 103005 GDNI
فروق جرد / Scrap       400036 Write Off Inventory
```
- **التحويل** (S1، المخزون اللي كان موجود): مدين Inventory / دائن 400001، لأن القطع اتسجلت مصروف وقت الشراء أيام الـ Periodic. وفي الـ go-live، مخزون أول المدة بيدخل بالجرد بنفس الطريقة.
  - Odoo بيرفض تغيير التقييم لفئة فيها منتج متقيّم بالسيريال (المولدات، `x4u_job_order` V6) وليه حركات، فالتقييم بالسيريال بيتقفل وقت التحويل ويرجع تاني. ده بيعمل قيدين بيقفلوا على صفر، والسيريال بيفضل بقيمته.
  - على `odoo4u_base` (2026-11-07): `STJ/2026/11/0001` مدين 103002 بـ 40,800 / دائن 400001. المخزون في الميزانية = تقرير المخزون = 40,800، والمولد `MO006` بقيمته.
  - داتابيز جديدة (`create-db.ps1`) بتتعمل Perpetual من الأول، من غير تحويل.
- 🔵 للمحاسب: الأكواد.

## 10. Landed Costs: الشحن والتأمين والتخليص والجمارك في تكلفة المخزون (v0.5، 2026-11-07)
المستخدم وافق على التصميم، والتوزيع بالقيمة. اتنفّذت في `x4u_account` 18.0.1.4.0 (Odoo `stock_landed_costs`). ده بيقفل **M3** من مراجعة الحسابات.

| المنتج | الفئة | حساب التسوية (Clearing) | التوزيع |
|---|---|---|---|
| Freight | Landed Costs / Freight | 103018 Shipment Other Charges | بالقيمة |
| Shipment Insurance | Landed Costs / Insurance | 103016 Shipment Insurance | بالقيمة |
| Clearing & Documentation | Landed Costs / Clearing & Documentation | 103017 Shipments Documentation Charges | بالتساوي على السطور |
| Customs Duty | Landed Costs / Customs Duty | **103021 Customs Duty Clearing** (جديد) | بالقيمة، ومن غير VAT |

الدورة:
```
فاتورة الشاحن / المخلّص   مدين 1030xx Clearing (+ VAT لو فيه) / دائن 201002 الموردين
Create Landed Costs ← تختار الاستلام (Receipt) ← Compute ← Validate
                          مدين 1030xx Inventory              / دائن 1030xx Clearing
```
- كل فئة حساب الـ Expense والـ Stock Input بتوعها هما حساب التسوية، علشان الفاتورة تدخل فيه والـ Landed Cost يطلّع منه، فيقفل على صفر.
- **ضريبة الاستيراد** (5% Reverse Charge) ضريبة مستردة ومش جزء من التكلفة، وبتفضل في `5% R C`.
- لو جزء من البضاعة اتصرف أو اتباع قبل الـ Validate، Odoo بيحمّل نصيبه على التكلفة (COGS) لوحده.
- 🔵 للمحاسب: رصيد حسابات التسوية آخر الشهر = مصاريف اتدفعت ولسه مااتحمّلتش على شحنة، فلازم تتراجع.

## 11. الأصول الثابتة (v0.6، 2026-11-07)
المستخدم وافق على الفئات والأعمار. اتنفّذت في `x4u_account` 18.0.1.5.0 (OCA `account_asset_management`). ده بيقفل **H4** من مراجعة الحسابات.

| الفئة (Profile) | الأصل | مجمع الإهلاك | مصروف الإهلاك | العمر |
|---|---|---|---|---|
| Leasehold Improvements | 106001 | 106006 | 400063 | 5 سنين |
| Furniture & Office Equipment | 106002 | 106007 | 400064 | 5 سنين |
| Computer Hardware & Software | 106003 | 106008 | 400065 | 3 سنين |
| Motor Vehicles | 106004 | 106009 | 400066 | 5 سنين |
| Right-of-Use Assets (IFRS 16) | 100101 | 100102 | 400070 | مدة العقد (الافتراضي 5) |

- قسط ثابت، شهري، بالنسبة والتناسب من تاريخ الشراء، على journal جديد **AST Fixed Assets**.
- **الربط**: كل حساب أصل مربوط بالـ Profile بتاعه، فأي سطر في فاتورة مورد على 106002 مثلًا **بيعمل الأصل لوحده** وقت الـ Confirm.
- قيد الإهلاك الشهري: مدين 4000xx مصروف الإهلاك / دائن 1060xx مجمع الإهلاك. والـ job بتاع OCA "Generate assets" اتشغّل، فالأقساط المستحقة بتتسجل لوحدها.
- 🔵 للمحاسب: الأعمار، والأصول اللي عندكم من قبل كده (تتدخل بتاريخها وقيمتها ومجمع إهلاكها).
