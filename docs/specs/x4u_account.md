# Spec — `x4u_account`: قوايم الحسابات، الـ PDC، حقوق الملكية، Receivables & Payables، والتسوية التلقائية — v0.2

- الحالة: **اتوافق عليها 2026-11-07** (طلب المستخدم، واختار "Full PDC cycle"). اتنفّذت في `x4u_account` 18.0.1.0.0، و `x4u_sale` 18.0.2.1.1، و `x4u_purchase` 18.0.1.0.1.
- v0.2 (2026-11-07): الطلب التاني (Journal Items، Petty Cash، الـ Capital، Payments + Due List، التسوية التلقائية، Receivable & Payable) ← §1 (1b، 2b)، §2 P8، §3، §4، §5. المستخدم اختار الاقتراح في الأربع أسئلة. اتنفّذت في `x4u_account` 18.0.1.1.0.
- v0.7 (2026-11-07): المرحلة 5، الرقابة والتقارير ← §12 شيكات العملاء، §13 القفل الشهري والسنة المالية، §14 التقارير الإدارية، §15 الربحية لكل Job Order. المستخدم اختار الاقتراح في الأربع أسئلة. اتنفّذت في `x4u_account` 18.0.1.6.0 و `x4u_job_order` 18.0.1.5.0.
- v0.9 (2026-11-19، ✅ المستخدم: "شهر 1 مثلا مصاريفنا كانت كام ومرتبات وكهرباء وكل حاجه ودخلنا كام وصافي الربح كام"): **4U Monthly P&L**، عمود لكل شهر في السنة والإجمالي (§17). بتتنفّذ في `x4u_account` 18.0.1.8.0. وربحية كل أوردر في [x4u_job_order §0.14](x4u_job_order.md).
- v0.8 (2026-11-18): **قايمة Reporting كاملة** زي الصور اللي بعتها المستخدم (§16). المستخدم اختار: **مترتبة من غير تكرار**، و**تقارير الـ Excel تفتح الشاشة وتدوس Export XLSX**، و**MIS Budgets**. بتتنفّذ في `x4u_account` 18.0.1.7.0.
- v0.10 (2026-11-21، ✅ المستخدم: "حمله"): **سعر الإسترليني كل يوم** من الـ ECB عن طريق ربط الدولار (§18). بتتنفّذ في `x4u_account` 18.0.1.9.0 مع OCA `currency_rate_update`.
- v0.11 (2026-11-24، ✅ المستخدم: "الاتنين بيستخدموا نفس شجره الحسابات فعاوزك تطبقها علي الفور يو بردو وبعدين هنعمل زيها علي ال ata"، و "علشان نطبها ونسحب منها تقارير"): **شجرة حسابات Focus** على 4U و ATA (§19). بتتنفّذ في `x4u_account` 18.0.1.10.0.
- v0.12 (2026-11-24، UAT مع المحاسبين على الـ pilot، Phase 1؛ ✅ المستخدم: "خليه زي ماهم عاوزين"، و "عاوز سعرها الماتيريال الي موجوده تتسعر بالقيمه الي بنشتريها من الموردين والسعر العام يكون هو المتوسط"، و "سيبك من ال ATA خالص دلوقت"): **تقييم المخزون والتصنيع والسيريال** (§20). بتتنفّذ في `x4u_account` 18.0.1.11.0 و `x4u_job_order` 18.0.1.16.0، على 4U بس.
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

- **التقييم**: Automated (Perpetual) + **Anglo-Saxon**، بـ FIFO، على فئات المكونات والمولدات وقطع الغيار. الخدمات والمصروفات زي ما هي. **من v0.12 (§20)**: بالمتوسط (AVCO) بدل FIFO، وتكلفة المبيعات مع التسليم بدل GDNI.
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
- **S6، الفاتورة قبل التسليم** (اتلقت واتصلّحت 2026-11-07، `x4u_account` 18.0.1.6.1): في دورة 4U، الفاتورة الضريبية بتطلع قبل ما المولد يتصنع. Odoo بيسعّر تكلفة المبيعات وقت الفاتورة، وساعتها قيمة المولد صفر، فمابيسجلش COGS خالص. والتسليم بعد كده بيعمل مدين 103005 / دائن 103002 بس، فالتكلفة كانت هتفضل في GDNI ومش هتوصل للـ P&L، والـ Gross Margin والربحية كانوا هيطلعوا أعلى من الحقيقة.
  - **الحل**: لما سطر البيع يبقى كل اللي اتسلّم منه اتفوتر (والعكس)، اللي فاضل في GDNI للسطر ده بيتنقل لتكلفة المبيعات بالقيمة الحقيقية، **عليه الـ Analytic بتاع الـ Job Order**، والسطور بتتقفل (Reconcile). القيد: مدين 400001 COGS / دائن 103005 GDNI، في journal المخزون، اسمه "Cost of sales S0xx - المولد".
  - بيشتغل بعد كل تسليم وبعد كل فاتورة. ولو التسليم جه الأول، Odoo بيسجل التكلفة الصح بنفسه، فمفيش قيد زيادة.
  - لو السطر فيه أكتر من وحدة واتسلّم جزء، التكلفة بتتسجل لما يكمل التسليم.
  - اتجرّب (`x4u_job_order` T20): فاتورة الأول ← تصنيع ← تسليم: COGS = 2,160 (القطع 1,800 + 20%)، و GDNI = صفر، وربح الـ Job = 7,840.
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

## 12. الشيكات الآجلة من العملاء (v0.7، 2026-11-07)
المرحلة 5. المستخدم اختار "Reopen invoice". اتنفّذت في `x4u_account` 18.0.1.6.0 على OCA `account_check_deposit`. ده بيقفل **M4** من مراجعة الحسابات.

| # | الخطوة | القيد |
|---|---|---|
| K1 | Journal **CHK "PDC Received"** (نوعه Bank، وترتيبه بعد البنوك الحقيقية)، والـ Manual بتاعه على `102013 Post Dated Cheques Received` (بقى Reconcile) | — |
| K2 | **استلام الشيك**: من الفاتورة ← Pay ← Journal "PDC Received"، ورقم الشيك وتاريخه **إجباري**. الرقم ممنوع يتكرر لنفس العميل (عملاء تانيين ممكن يبقى عندهم نفس الرقم من بنوك تانية). الحالة **In Hand**، والفاتورة **In Payment** | مدين 102013 / دائن العميل |
| K3 | **الإيداع**: Customers ← **Cheque Deposits** ← Get All Received Checks بيجيب **الشيكات اللي تاريخها جه بس**، والـ Validate بيرفض أي شيك تاريخه بعد يوم الإيداع. الحالة **Deposited**، والفاتورة لسه In Payment | مدين Outstanding Receipts بتاع البنك / دائن 102013 |
| K4 | **سطر لكل شيك** على ناحية البنك (مش سطر واحد بالإجمالي)، عليه رقم الشيك واسم العميل. فكل شيك بيتقفل لوحده مع كشف البنك يوم ما البنك يصرفه ← **Cleared**، والفاتورة **Paid** | كشف البنك: مدين Bank / دائن Outstanding Receipts |
| K5 | **Cheque Bounced**: قبل الإيداع، الدفعة بتتلغي وبتطلع من الإيداع لو لسه Draft. بعد الإيداع، قيد جديد في journal البنك بيرجّع المديونية، والفاتورة **بترجع مفتوحة**، وناحية البنك بتتقفل فمفيش حاجة تستنى كشف | مدين العميل / دائن Outstanding Receipts |

- قايمة **Customers ← PDC Received**: الشيكات بتاريخها، وفلاتر In Hand، و Deposited، و "Cheque Date Passed"، و "Due in 7 Days".
- قايمة PDC Cheques (الموردين) بقت للدفعات الطالعة بس.
- ⏳ شاشة الإيداع (OCA) بتعرض بنوك عليها **رقم حساب (IBAN)** بس، فالإيداع الحقيقي بييجي مع المرحلة 3.

## 13. القفل الشهري والسنة المالية (v0.7، 2026-11-07)
المستخدم اختار "Auto soft + manual" و "Jan - Dec". ده بيقفل **M1**.

| # | القفل | مين / إمتى |
|---|---|---|
| L1 | **Sales و Purchase Lock** لآخر الشهر اللي فات | **أوتوماتيك يوم 10** من كل شهر (job كل يوم، وبيقدّم التاريخ بس، ومابيرجعهوش). أي فاتورة أو bill بتاريخ قديم Odoo بيسجلها في أول يوم مفتوح. اليوم بيتغير من `x4u_account.soft_lock_day` في System Parameters |
| L2 | **Global Lock** (كل القيود) بعد خطوات القفل، و **Tax Lock** بعد كل إقرار VAT، و **Hard Lock** (مابيترجعش) بعد المراجعة | المدير المالي بس: Accounting ← Accounting ← **Lock Dates** (OCA `account_lock_date_update`). Odoo بيرفض الـ Global Lock لو فيه سطور كشف بنك لسه ماتسوّتش |
| L3 | **السنة المالية**: FY 2026 و FY 2027 (يناير–ديسمبر)، والسنين اللي بعد كده بتتعمل لوحدها (OCA `account_fiscal_year_auto_create`) | — |

**خطوات القفل الشهري (المدير المالي)**:
1. كشوف البنوك اتسوّت، والشيكات (PDC Issued و Received) اتراجعت.
2. الإهلاك اتسجل (Assets ← Compute Assets)، والمرتبات والمخصصات اتسجلت.
3. GRNI (201021) و GDNI (103005) وحسابات تسوية الـ Landed Costs اتراجعت.
4. سطر **"Accounts Not in This Report"** في الـ P&L (§14) بصفر.
5. **Global Lock** لآخر الشهر. وبعد إقرار الـ VAT، **Tax Lock**.

## 14. التقارير الإدارية (v0.7، 2026-11-07)
على OCA `mis_builder`، و `mis_template_financial_report`. ده بيقفل **M6**. المكان: Accounting ← Reporting ← MIS Reporting ← **MIS Reports**، وكل تقرير بيطلع PDF و Excel.

| التقرير | الأعمدة | المحتوى |
|---|---|---|
| **4U Management P&L** | This Month، Last Month، Year to Date، Last Year | المبيعات (مولدات 500001، قطع غيار 500015، خدمات 500008، أخرى) ← تكلفة المبيعات ← **Gross Profit و Gross Margin %** ← المصروفات في 11 مجموعة (الموظفين، المقر، الاتصالات، السفر، الأتعاب والرخص، الإعلان، السيارات، الإدارية، البنك، المخصصات، والـ Overhead اللي اتحمّل على المولدات 400072) ← **EBITDA** ← الإهلاك ← **Operating Profit** ← إيرادات ومصروفات أخرى ← الضريبة ← **Net Profit و Net Margin %** |
| **4U P&L - Last 6 Months** | آخر 6 شهور، كل شهر لوحده، والإجمالي | نفس الـ P&L |
| **4U Cash & Working Capital** | النهارده، آخر الشهر اللي فات، آخر السنة اللي فاتت | البنك والكاش، و PDC Received، والعملاء، والمخزون، والموردين، و PDC Issued، و GRNI ← **Working Capital**، و **"الكاش بعد ما كل الشيكات تتصرف"** |
| **4U Balance Sheet** | نفس الأعمدة | قالب OCA بأنواع الحسابات |

- كل سطر ممكن يتفتح لحد الحسابات وبعدين القيود (drill-down).
- **"Accounts Not in This Report (must be 0)"**: أي حساب P&L جديد مش في المجموعات بيبان هنا، فالتقرير مابيخبيش حاجة.
- المجموعات بالأكواد الحالية (`l10n_ae`) في `data/mis_report_data.xml`. 🔵 لما شجرة الحسابات الجديدة تتعمل (docs/modules/06-accounting.md §5)، المجموعات بتتغير هناك. والمحاسب ممكن يعمل نسخة (Duplicate) ويعدّل عليها من الشاشة.

## 15. الربحية لكل Job Order (v0.7، 2026-11-07)
المستخدم اختار "Each Job Order". اتنفّذت في `x4u_job_order` 18.0.1.5.0. ده بيقفل **M2**.

- كل Job Order (MO001) ليه **Analytic Account** لوحده (الكود = رقم الـ Job Order، والاسم = العميل) في plan **"Job Orders"**.
- الـ Analytic بيتحط على **سطر البيع** بتاع المولد، ومن هناك بيروح للفاتورة (الإيراد)، وللدفعة المقدمة، ولـ **تكلفة المبيعات** (Anglo-Saxon). لو سطر واحد فيه مولدين، بيتقسم 50/50.
- مصاريف الـ Job المباشرة (نقل، ونش، تركيب، مقاول) بتتحط على سطر الـ bill بالـ Analytic بتاعه (عمود Analytic بقى ظاهر).
- **مش** على قطع المخزون: القطع بتدخل المخزون وبعدين في قيمة المولد، فبتوصل للربحية مع تكلفة المبيعات من غير تكرار.
- Accounting ← Reporting ← **Job Profitability** (Pivot: لكل Job Order الإيراد والتكلفة بالحساب، والإجمالي = الربح)، وزرار **Margin** على الـ Job Order.
- الـ Job Orders اللي كانت موجودة خدت الـ Analytic بتاعها وقت الـ upgrade، هي وسطور فواتيرها وتكلفة مبيعاتها.

## 16. قايمة Reporting كاملة (v0.8، 2026-11-18) ✅
طلب المستخدم: "عاوز قائمة الـ reporting في الحسابات تضمن كل التابات دي وتشتغل بشكل احترافي". الصور من سيستم تاني متثبت عليه موديولين تقارير، فيها تقارير متكررة. المستخدم اختار: **مترتبة من غير تكرار** (نفس المجموعات والأسماء، كل تقرير مرة واحدة)، و**الـ Excel يفتح الشاشة وتدوس Export XLSX**، و**MIS Budgets**. كله على Odoo Community و OCA من الـ repos المتثبتة (مفيش pin جديد).

### 16.1 القايمة: Accounting ← Reporting
| المجموعة | التقرير | بيشتغل بإيه |
|---|---|---|
| **Generic Statements** | Profit and Loss | 4U Management P&L (MIS)، بيفتح على طول |
| | Balance Sheet | 4U Balance Sheet (MIS) |
| | Cash Flow Statement | **جديد**: 4U Cash Flow Statement (MIS، الطريقة غير المباشرة، R1) |
| **Daily Reports** | Bank Book | General Ledger (OCA) على حسابات البنك (journals نوع Bank، من غير PDC Received) |
| | Cash Book | General Ledger على حسابات الكاش (journals نوع Cash) |
| | Day Book | Journal Ledger (OCA) على النهارده، كل الـ journals |
| **Partner Reports** | Partner Ledger | General Ledger على حسابات العملاء والموردين، متجمّع بالعميل / المورد |
| | Aged Partner Balance | OCA |
| | Open Items | OCA |
| **Management** | Invoice Analysis | Odoo |
| | Budgets | **جديد**: OCA `mis_builder_budget`، Budget لكل حساب ولكل فترة (R2) |
| | Assets | `account_asset_management`: قايمة الأصول |
| | Assets Analysis | `account_asset_management` (Pivot) |
| | Analytic Report، Audit Trail، Job Profitability | زي ما هم |
| **Audit Reports** | General Ledger | OCA |
| | Trial Balance | OCA |
| | Journals Audit | Journal Ledger (OCA) |
| | Tax Report | VAT Report (OCA) |
| | Tax Details Report | **جديد**: OCA `account_tax_balance`: لكل ضريبة الأساس والضريبة، وتفتح لحد القيود |
| **Financial Reports** | Financial Statement | القوايم المالية بتاعة 4U (MIS): تختار واحدة وتشوفها أو تطبعها PDF / Excel |
| | Assets Schedule | Financial Assets report (`account_asset_management`، Excel) |
| **Excel Reports** | Accounts Receivable (Excel) | Open Items على حسابات العملاء ← Export XLSX |
| | Accounts Payable (Excel) | Open Items على حسابات الموردين ← Export XLSX |
| | Trial Balance (Excel) | Trial Balance ← Export XLSX |
| | Balance Sheet (Excel) | 4U Balance Sheet ← Export |
| | Profit / Loss (Excel) | 4U Management P&L ← Export |
| **My Dashboard** | | My Dashboard بتاع Odoo (أي تقرير يتضاف له بـ "Add to my dashboard") |
| **MIS Reporting** | MIS Reports، Last Reports Generated | OCA |

- مجموعة **OCA accounting reports** و **Financial Assets** و **Taxes Balance** بتاعة OCA بتتشال من القايمة، لأن تقاريرهم اتوزعت فوق. و **Budgets (by KPIs)** بتاعة OCA بتستخبى (Budgets بالحساب هي المستعملة).
- كل تقرير OCA بيتفتح شاشة فيها الفترة والفلاتر، وفيها **View** (على الشاشة)، و **Export PDF**، و **Export XLSX**. وتقارير MIS بتتفتح على طول، وفيها **Print** و **Export**، وكل رقم بيتفتح لحد القيود.
- الصلاحيات: المحاسب، و Accounting Manager، والمدير العام، زي تقارير OCA.

### 16.2 القواعد
| # | القاعدة | الحالة |
|---|---|---|
| R1 | **4U Cash Flow Statement** (الطريقة غير المباشرة، بأنواع الحسابات، فبيمشي مع أي حساب جديد): صافي الربح، + الإهلاك، ± التغير في العملاء، والمخزون، والأصول المتداولة التانية، والموردين، والالتزامات المتداولة التانية ← **Operating**؛ شراء الأصول الثابتة ← **Investing**؛ القروض، ورأس المال وحقوق الملكية ← **Financing**؛ صافي التغير في الكاش، والكاش أول الفترة وآخرها، وسطر **"Check (must be 0)"**. الأعمدة: This Month، Year to Date، Last Year. ملحوظة: `mis_builder_cash_flow` بتاع OCA مش Cash Flow Statement، ده توقع للكاش من تواريخ الاستحقاق، فماستعملناهوش | ✅ |
| R2 | **Budgets**: المحاسب يعمل Budget بالحساب والفترة (شهر أو ربع سنة) من Management ← Budgets. وتقرير **4U P&L vs Budget** (Year to Date: Actual، Budget، Variance) بيتعمل على أول Budget للسنة الحالية | ✅ المستخدم |
| R3 | **Bank Book / Cash Book / Partner Ledger / AR / AP (Excel)** بيفتحوا شاشة OCA بالحسابات متحطة (من الـ journals وأنواع الحسابات وقت الفتح، فأي بنك جديد بيدخل لوحده). والفترة وكل الفلاتر تتغير قبل View أو Export | ✅ المستخدم |

### 16.3 الـ upgrade
- `x4u_account` 18.0.1.7.0 بيعتمد على `mis_builder_budget` و `account_tax_balance` (OCA، من `mis-builder` و `account-financial-reporting` المتثبتين).
- backup لـ `odoo4u_base` الأول، وتجربة على نسخة، وبعدين upgrade.

### 16.4 Tests
| # | الاختبار |
|---|---|
| T1 | القايمة: كل الأسماء في المجموعات بتاعتها، ومفيش "OCA accounting reports" |
| T2 | Bank Book بيفتح General Ledger على حسابات البنك بس، و Cash Book على الكاش، و Partner Ledger متجمّع بالعميل على العملاء والموردين، و AR (Excel) على العملاء بس |
| T3 | Cash Flow Statement: فاتورة بيع ودفعتها، وشراء أصل، وقرض: Check = 0، وصافي التغير = حركة البنك |

## 17. الـ P&L شهر بشهر (v0.9، 2026-11-19) ✅
| # | القاعدة | الحالة |
|---|---|---|
| M1 | **4U Monthly P&L YYYY**: نفس بنود 4U Management P&L (المبيعات بأنواعها، وتكلفة المبيعات، و Gross Profit، والمصروفات في مجموعاتها وكل حساب جواها: مرتبات، وإيجار، وكهرباء…، والـ Overhead اللي اتحمّل على المولدات، و EBITDA، والإهلاك، و **Net Profit**)، بعمود لكل شهر من يناير لديسمبر، وعمود **Total**. وكل رقم بيتفتح لحد القيود | ✅ المستخدم |
| M2 | **فين**: Reporting ← Generic Statements ← **Monthly Profit and Loss** (بيفتح السنة الحالية)، وكل سنة ليها تقرير بيتعمل لوحده أول ما السنة تبدأ (cron شهري، أو أول مرة تفتحه) | ✅ |
| M3 | **الـ Overhead**: سطر "Overhead applied" (400072، دائن) في المصروفات بيتقابل مع المصروفات الحقيقية (مرتبات العمال، والكهرباء، والنقل)، فالمحاسب يشوف كل شهر النسبة مغطية المصروفات ولا لأ | ✅ |

| # | الاختبار |
|---|---|
| T4 | Monthly P&L: 12 عمود + Total للسنة الحالية، بيتعمل مرة واحدة، والقيد في مارس بيظهر في عمود مارس والإجمالي |

## 18. سعر الإسترليني كل يوم (v0.10، 2026-11-21) ✅
أسعار Perkins بالإسترليني، والسعر لازم يبقى السعر العالمي لايف ويتحول لدرهم (المستخدم: "مظبوط علي حسب السعر العالمي لايف يتحول لدرهم"، و "حمله").

| # | القاعدة | الحالة |
|---|---|---|
| G1 | OCA **currency_rate_update** 18.0.1.0.1 (OCA/currency، 18.0 @ e7d64f8، 2026-11-11). بيجيب الأسعار من **البنك المركزي الأوروبي (ECB)** كل يوم (cron "Currency Rates Update (OCA) daily") | ✅ |
| G2 | الـ ECB مافيهوش درهم. فـ 4U عندها مصدر خاص **"ECB via the USD peg (AED)"**: الإسترليني قصاد الدولار من الـ ECB، وبعدين الدولار بالربط **3.6725** (§8 Q1). الدولار نفسه مابيتغيرش، فضل على 3.6725 | ✅ |
| G3 | العملات: **GBP** بس. المحاسب يزود أي عملة تانية عند الـ ECB (EUR مثلا) من Accounting ← Configuration ← **Currency Rates Providers** | ✅ |
| G4 | الـ ECB بينزّل السعر في أيام الشغل حوالي الساعة 4 العصر بتوقيت أوروبا. يوم الإجازة Odoo بياخد آخر سعر قبله. لو الـ ECB وقع، المصدر بيكتب الغلط في الـ chatter بتاعه وبيحاول تاني اليوم اللي بعده | ✅ |

| # | الاختبار |
|---|---|
| T5 | ملف ECB تجريبي (1 EUR = 1.15 USD = 0.88 GBP): 100 GBP = 479.93 درهم، 100 USD فضلت 367.25، ومافيش سعر EUR أو USD اتكتب. المصدر بيتعمل مرة واحدة |

## 19. شجرة حسابات Focus (v0.11، 2026-11-24)
الفريق كان شغال على **Focus** (Focus Softnet). الشركتين، 4U و ATA SAIF ZONE، ليهم **نفس الشجرة**. المستخدم بعت شجرة ATA وميزان المراجعة ودفتر الأستاذ لحد 30-09-2026 كمثال (الملفات في `private/`، ومابتروحش Git). واختار **"The Odoo way"**: العملاء والموردين partners، والموظف على السطر.

| # | القاعدة | الحالة |
|---|---|---|
| F1 | **المجموعات** = شجرة Focus بالترتيب: 1 ASSETS (11 VAT ACCOUNT، 12 HOLD، 13 CURRENT ASSETS: 1311 CASH & Petty Cash، 1312 BANK، 132 PDC Receivables، 133 Customers، 134 INVENTORY، 135 DEPOSIT، 136 ADVANCE : EMPLOYEE، 137 Prepayments، 14 FIXED ASSETS)، 2 LIABILITIES (211 Suppliers، 212 Accrued - EXP، 213 Gratuity، 214 PDCP، 215 Employee Accrued، 22 LOANS، 23 Paid By Partner، 24 OWNERSHIP)، 4 Revenue (41 Income، 42 Cost Of Project)، 5 General EXP. (51 Salaries، 52 Visa Exp.، 53 Other Admin EXP.)، 9 Control Accounts (99 حسابات Odoo). الكود 6 أرقام: المجموعة وبعدها رقم الحساب | ✅ |
| F2 | **نفس الكود في الشركتين** (`x4u_account/focus_chart.py`). حساب شخص واحد (عهدة، جاري شريك) المحاسب بيضيفه في الأكواد الفاضية بتاعة مجموعته (1311xx، 2400xx) | ✅ |
| F3 | **"The Odoo way"**: العملاء على 133001 Customers، والموردين على 211001 Suppliers (كل واحد partner، فالـ aging والكشوف شغالة). سلف الموظفين 136001، والمرتبات 510001، والمرتبات المستحقة 215003، والموظف على السطر. الأصول الثابتة حساب لكل فئة، ومجمع إهلاك لكل فئة (14009x)، وكل أصل ليه كارت | ✅ |
| F4 | **التحويل**: كل حساب l10n_ae ليه مقابل في الشجرة بياخد كود Focus واسمه، والقيود والـ journals والإعدادات بتفضل زي ما هي (مثلا 102011 ← 133001، 201021 GRNI ← 212006، 103001 ← 134004، 400072 ← 530082). اللي ناقص بيتعمل. وحساب ليه كود Focus بالفعل مابيتغيرش (بتاع المحاسب) | ✅ |
| F5 | **التنضيف**: حسابات l10n_ae اللي برا الشجرة ومش مستخدمة في أي حاجة (قيد، journal، ضريبة، إعداد) بتتمسح. والمستخدم منها بيروح مجموعة 99 | ✅ |
| F6 | **التقارير**: 4U Management P&L، و Cash & Working Capital، و Cash Flow على أكواد الشجرة. وقوايم Generic Statements بتعرض **الشركة المختارة فوق**، مش الشركة اللي ثبتت الموديول | ✅ |
| F7 | **Profit/Loss A/C** (900002) = أرباح محتجزة (Odoo: current year earnings) | ✅ |
| F8 | **الـ Balance Sheet** بيتوزن في كل عمود: "Today" و "End of Last Month" بقوا من أول السنة (Year to date)، فربح السنة لحد التاريخ ده داخل. قبل كده كان بيحسب ربح يوم واحد أو شهر واحد، فالأصول ماكانتش بتساوي الالتزامات وحقوق الملكية (اتلقطت في اختبار التقارير على داتا التدريب، 2026-11-24) | ✅ |

**ATA في داتابيز التدريب** (2026-11-24): شجرة Focus، و 769 partner، وأرصدة أول المدة يوم 01-01-2026، و 889 قيد من Focus (يناير–سبتمبر). ميزان المراجعة بتاع Odoo يوم 30-09-2026 = ميزان Focus، حساب حساب وعميل عميل. فرقين بس، الاتنين من Focus نفسه: (1) SALES OTHERS بـ 3,500 (فاتورة ATA/034) موجود في دفتر الأستاذ ومش في الميزان، وأرصدة أول المدة مش متوازنة بنفس المبلغ (900099). (2) Accm Depreciation اتنقل من الالتزامات للأصول الثابتة. السكريبتات في `private/ata/` (فيها بيانات الشركة).

| # | الاختبار |
|---|---|
| T7 | Balance Sheet: قيد بيع في السنة دي، والأصول = الالتزامات + حقوق الملكية في كل عمود، وربح السنة فيه |
| T6 | بعد الـ setup: مجموعات الشجرة كلها، وكل حساب بيستعمله الموديول بكود Focus، ومفيش 102011 / 201002 / 103001 / 201021 / 999999، والعملاء تحت Customers ← CURRENT ASSETS، و 900002 نوعه equity_unaffected، و PDCP 214001، والـ P&L مش مربوط بشركة |

## 20. Phase 1 بعد الـ UAT: تقييم المخزون والتصنيع والسيريال (v0.12، 2026-11-24) ✅
المحاسبين جرّبوا دورة كاملة على الـ **pilot** (شراء ← تصنيع ← بيع) ولقوا إن الاستلام بيروح على **COGS** على طول، والـ MO بيحرّك الكميات من غير فلوس، والسيريال مش ظاهر. السبب اتلقى في الداتا: المنتجات الـ 3 اللي اتعملت للتجربة (`ckd 100kva cummins`، و `canopy parts 100kva cummins`، و `CUMMINS READY 100KVA`) اتسجلت في فئة **All**. الفئة دي Periodic، فـ: فاتورة المورد راحت 150,000 على Cost of Goods Sold، والـ MO ماعملش قيد، ومفيش سيريال (Tracking: None). الفئات بتاعة 4U نفسها كانت متظبطة صح (اتأكدت على نسخة التدريب: الاستلام مدين 134004 / دائن 212006).

القرارات: ATA برا الموضوع دلوقتي (المستخدم: "سيبك من ال ATA خالص دلوقت"). سيريال الدينامو مافيش فيه تغيير.

| # | القاعدة | الحالة |
|---|---|---|
| P1 | **منتج مخزون في فئة مخزون بس**: أي منتج عليه Track Inventory لازم فئته تكون Automated (Engines، CKD، Genset Bodies، Alternators، Generator Components، Generators، Spare Parts). في All أو Saleable أو Expenses أو Services، Odoo بيرفض الحفظ وبيقول الفئات المسموحة. ده على الشركات اللي فيها Anglo-Saxon بس (4U) | ✅ |
| P1 | **السعر بالمتوسط (AVCO)**: الخامة بتدخل بسعر شرايها من المورد، وسعر المنتج العام = المتوسط المرجّح للي في المخزن. الماتور والـ CKD والـ Canopy والمولد كل سيريال بتكلفته هو (Lot Valuation)، والمنتج بيعرض متوسط السيريالات اللي في المخزن. المولد قيمته في المخزن = تكلفة تجميعه (سيريالات قطعه بسعر شرايها + الـ Overhead)، وسعر البيع بييجي من عرض السعر بتاع السيلز، مش من المخزن (IAS 2: المخزون بالتكلفة) | ✅ |
| P1 | **التحويل من FIFO** على داتابيز فيها مخزون: الطريقة بس اللي بتتغير، وكل سيريال ومنتج سعره = قيمته ÷ كميته. مفيش قيد ومفيش إعادة تقييم، لأن القيمة هي هي | ✅ |
| P2 | **تكلفة المبيعات مع التسليم** (طلب المحاسبين): التسليم مدين 421001 Cost of Sales / دائن المخزون، وعليه الـ Analytic بتاع الـ Job Order (ربحية الأوردر). الفاتورة فيها الإيراد والضريبة بس. حساب الـ Stock Output للفئة = حساب تكلفة المبيعات بتاعها، و GDNI (134006) مابقاش بيتستعمل | ✅ |
| P2 | **اللي كان فاضل في GDNI** وقت التحويل بيروح لتكلفة المبيعات، لكل منتج وسطر بيع: اتسلّم ومااتفوترش ← تكلفة دلوقتي، اتفوتر ومااتسلّمش ← تكلفة الفاتورة بترجع والتسليم بيسجلها | ✅ |
| P3 | **السيريال ظاهر**: على المولدات كمان (فئة Generators = سيريال إجباري، زي الماتور والـ CKD والـ Body)، وفي اسم كل قيد مخزون ("... - SN E-1001")، وعمود **Serial Numbers** في ليستة الـ Receipts والـ Deliveries (والبحث بيه)، وعمود Generator Serial في ليستة الـ MO، وعلى الـ Delivery Slip | ✅ |

القيود دلوقتي (مثال: خامات 66,000، Overhead 20%):
```
استلام من المورد        مدين 134004 Stock - Raw Material 66,000   / دائن 212006 GRNI 66,000
فاتورة المورد           مدين 212006 GRNI + 110xxx VAT In           / دائن 211001 Suppliers
تصنيع: صرف الخامات      مدين 134002 WIP 66,000                     / دائن 134004 66,000
تصنيع: المولد خلص       مدين 134001 Stock - Finished Goods 79,200  / دائن 134002 WIP 66,000 + 530082 Overhead Applied 13,200
تسليم للعميل            مدين 421001 Cost of Sales 79,200 (Analytic) / دائن 134001 79,200
فاتورة العميل           مدين 133001 Customers                      / دائن 410002 Sales Generators + VAT Out
```

| # | الاختبار |
|---|---|
| T8 | منتج مخزون في All بيترفض (إنشاء، أو Track Inventory، أو تغيير الفئة)، والـ Consumable العادي في All مسموح |
| T9 | دينامو مرتين بـ 1,000 و 1,200: السعر 1,100. ماتورين بـ 1,000 و 1,400: كل سيريال بسعره، والمنتج 1,200 |
| T10 | فئة FIFO فيها سيريالين بـ 500 و 700: بعد التحويل AVCO، نفس الـ layers، والسيريالات 500 و 700، والمنتج 600 |
| T11 | دورة كاملة: الاستلام عليه السيريال في اسم القيد، والتسليم مدين Cost of Sales / دائن Finished Goods، والفاتورة من غير سطور COGS، ومفيش GDNI. ورصيد GDNI قديم بيروح لتكلفة المبيعات |

سكريبت الـ UAT للمحاسبين: [docs/uat/phase1-inventory-accounting.md](../uat/phase1-inventory-accounting.md).
