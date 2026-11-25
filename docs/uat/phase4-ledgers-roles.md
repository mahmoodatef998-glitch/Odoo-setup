# UAT — Phase 4: الـ General Ledger والـ Partner Ledger وتجربة كل role

الهدف: المحاسبين يقروا الدفاتر من غير ما يصدّروا Excel: الحساب المقابل باين، والرصيد مكتوب Dr أو Cr، والضغط على أي سطر يفتح المستند. وبعدين كل role يجرب شغله بالمستخدم بتاعه. الشرح في [x4u_account §22](../specs/x4u_account.md).

> بعد الـ upgrade اعمل `docker compose restart web` وبعدها Ctrl+F5 في المتصفح، علشان الشاشات تاخد الكود الجديد.

## 1. Cash Book (الـ Petty Cash) والحساب المقابل (Accountant)
- اعمل صرف من الـ Petty Cash، مثلًا 2,000 بنزين على `530046 Petrol` (Journal Entry أو Petty Cash).
- Accounting ← Reporting ← Daily Reports ← **Cash Book** ← View.
- ✅ عمود **Counterpart** جنب Partner: مكتوب فيه `530046 Petrol`.
- ✅ الرصيد مكتوب **`2,000.00 AED Cr`** (مش `-2,000.00`).
- Accounting ← Accounting ← **Journal Items**: ✅ عمود Counterpart موجود (لو مش ظاهر: من ⋮ اللي في آخر الأعمدة).

## 2. الضغط على السطر (Accountant)
- في نفس التقرير اضغط **مرة واحدة** على التاريخ، أو الوصف، أو المبلغ ← ✅ بيفتح **القيد نفسه** (الفاتورة، أو الـ Bill، أو الـ Journal Entry).
- ارجع (Breadcrumb) ← اضغط على الشريك ← ✅ بيفتح كارت الشريك. واضغط على الحساب ← ✅ بيفتح الحساب.
- جرّب نفس الكلام في **General Ledger**، و **Bank Book**، و **Open Items**.

## 3. Partner Ledger و Dr / Cr (Accountant)
- عميل وهو مورد كمان: فاتورة بيع له، و Bill منه.
- Accounting ← Reporting ← Partner Reports ← **Partner Ledger** ← View:
  - ✅ تحت **133001 Customers**: الشريك برصيد **Dr** (ليه عندنا).
  - ✅ تحت **211001 Suppliers**: نفس الشريك برصيد **Cr** (لينا عليه)، كل واحد لوحده من غير ما يتخلطوا.
- **Customer Ledger** ← ✅ العملاء بس. **Vendor Ledger** ← ✅ الموردين بس، والرصيد Cr.
- Export (Excel) ← ✅ الرصيد مكتوب Dr / Cr، وفي نفس الوقت رقم (اعمل SUM وهيشتغل)، وعمود Counterpart موجود.

## 4. تجربة كل role
مستخدمين التجربة: `.\scripts\dev-users.ps1 -Database odoo4u_base` (الأدمن يحط باسورد من Settings ← Users).

| الـ Role | المستخدم | يقدر | مايقدرش |
|---|---|---|---|
| Purchasing Officer | x4u.purchasing@example.com | RFQ من طلب المواد، PO، **Print PO**، يستلم بالسيريال | Accounting، تعديل الـ MO، الـ Approve |
| Storekeeper | x4u.store@example.com | يستلم ويركّب الـ **Delivery Note** ويكتب السيريال، يسلّم للعميل | يشتري، يفوتر، Accounting |
| Operation Manager | x4u.production@example.com | Job Order: **Deliver Materials** و **Finish**، يوافق على الـ PO | Settings و Apps |
| Accountant | x4u.accountant@example.com | الـ Bill من الـ Receipt، الفواتير، الدفعات، **General Ledger / P&L / Balance Sheet** | يعمل أوردر بيع أو PO |

- ادخل بكل مستخدم ← اعمل الحاجة اللي في "يقدر" ← ✅ بتعدّي. وحاول تعمل واحدة من "مايقدرش" ← ✅ المنيو مش ظاهرة أو Odoo بيرفض.

لو أي خطوة طلعت مختلفة، ابعتولي صورة الشاشة.
