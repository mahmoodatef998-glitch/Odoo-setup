# UAT — Phase 3: الترقيم، والـ VAT 5%، والطباعة، والـ TRN

الهدف: الحسابات يتأكدوا إن الـ PO بيتطبع بعد الـ Confirm، وفواتير العملاء والموردين مترقّمة بشكل واحد، والـ TRN متسجل صح وإجباري للجهات المسجلة، والـ VAT 5% بيروح على VAT OUT و VAT IN كل واحد لوحده. الشرح في [x4u_account §21](../specs/x4u_account.md) و [x4u_purchase §9](../specs/x4u_purchase.md).

## 1. طباعة الـ PO (Purchasing)
- Purchase ← Orders ← New: مورد وصنف ← **Print RFQ** (زي الأول).
- Confirm (والـ GM يعمل Approve لو طلب).
- ✅ فوق، زرار **Print PO** ظاهر، سواء الـ PO كان To Approve أو Purchase Order أو Locked ← بيطلع الـ PDF بشروط الدفع والـ Payment Mode.

## 2. الـ TRN على كارت العميل والمورد (Accountant)
- Contacts ← New: شركة، البلد **United Arab Emirates**.
- في خانة **TRN** اكتب `12345` ← Save ← ✅ لازم يرفض: *The TRN of … must be 15 digits*.
- اكتب TRN صح (15 رقم، مثلًا `100123456700003`) ← Save ← ✅ **VAT Registered (UAE)** اتعلّمت لوحدها.
- كارت مورد أجنبي (مثلًا United Kingdom) برقمه الضريبي `GB123456789` ← ✅ بيتحفظ عادي.
- Contacts ← Filters ← **VAT Registered without TRN** ← الجهات اللي ناقصها TRN.

## 3. الـ TRN وقت الـ Confirm (Accountant)
- شركة في الإمارات من غير TRN: علّم **VAT Registered (UAE)** باليد ← Save.
- فاتورة عميل لها ← Confirm ← ✅ لازم يرفض: *… is VAT registered but has no TRN*. ونفس الكلام في Bill من مورد.
- ضيف الـ TRN على الكارت ← ارجع للفاتورة ← Confirm ← ✅ بتعدّي.
- فاتورة لعميل فرد من غير TRN (مش VAT Registered) ← ✅ بتعدّي.
- اطبع الفاتورة ← ✅ مكتوب **TRN: 100…** تحت اسم العميل (مش Tax ID).

## 4. الترقيم (Accountant)
- فاتورة عميل ← Confirm ← ✅ الرقم `4U-INV-2026-xxxx` (زي ما هو).
- Bill من مورد ← Confirm ← ✅ الرقم **`4U-BILL-2026-0001`**، والـ Bill اللي بعده `4U-BILL-2026-0002`.
- من الـ Bill ← Credit Note ← Confirm ← ✅ **`4U-VCN-2026-0001`**.
- ✅ الـ Bills القديمة اللي اترقّمت قبل كده (`BILL/2026/11/…`) بأرقامها زي ما هي.

## 5. VAT 5% في حسابين (Accountant)
- فاتورة عميل 1,000 بضريبة **5%** ← Confirm ← Journal Items ← ✅ 50 **دائن** على `110002 VAT OUT`.
- Bill 1,000 بضريبة شراء **5%** ← Confirm ← Journal Items ← ✅ 50 **مدين** على `110003 VAT IN`.
- Accounting ← Reporting ← Audit Reports ← **Tax Report** (أو Tax Details Report) ← ✅ ضريبة المبيعات والمشتريات كل واحدة في سطر.

لو أي خطوة طلعت مختلفة، ابعتولي صورة الشاشة.
