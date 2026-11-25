# UAT — Phase 2: الاستلام، والمرفقات، وفاتورة المورد

الهدف: فريق الحسابات والمخزن يتأكدوا إن الاستلام بيحصل بسيريال كل وحدة، والـ Delivery Note بتاع المورد بيتركّب، والمحاسب بيوصله إشعار بكل حاجة وصلت ورقم الفاتورة، وفاتورة المورد بتطلع من الاستلام بالكمية اللي وصلت. الشرح في [x4u_purchase §8](../specs/x4u_purchase.md).

اتجربت الدورة دي بالسكربت على نسخة من داتابيز التدريب، بمستخدمين طارق وأحمد (2026-11-25).

## 1. أمر الشراء (Purchasing)
- Purchase ← Orders ← New: مورد، وقطعة (مثلًا دينامو) **3 وحدات**، السعر 7,400 ← Confirm (والـ GM يعمل Approve لو طلب).

## 2. الاستلام (المشتريات / أمين المخزن)
- من الـ PO (Receive Products) أو Inventory ← Receipts.
- وصل **2 بس** من 3: اكتب الكمية 2، وسيريال كل وحدة في عمود Serials (الدينامو كمان). من غير السيريال الـ Validate بيترفض.
- اكتب رقم فاتورة المورد في **Vendor Invoice No.**
- دوس **Validate** من غير ما تركّب حاجة ← ✅ لازم يقول: *Attach the vendor's Delivery Note … before validating it*.
- في خانة **Delivery Note** فوق، ركّب صورة أو سكان الـ Delivery Note بتاع المورد ← Validate ← Create Backorder (الوحدة التالتة لما توصل).

## 3. المحاسب بيتبلّغ (Accountant)
- ✅ في الـ Inbox (Discuss) إشعار: *Goods received: WH/IN/xxxx from … (PO …)، Vendor invoice no.، والصنف بالكمية والسيريالات*، والـ Delivery Note مرفق.
- ✅ ومهمة (الساعة فوق): **Vendor bill: WH/IN/xxxx**.

## 4. فاتورة المورد من الاستلام (Accountant)
- Accounting ← Vendors ← Bills ← New: المورد و Bill Date.
- خانة **Receipt** ← اختار WH/IN/xxxx.
- ✅ السطر اتملى لوحده: الدينامو، الكمية **2** (مش 3)، السعر 7,400، ورقم فاتورة المورد في Bill Reference.
- Save ← ✅ في الـ chatter: *Documents of WH/IN/xxxx* ومعاها الـ Delivery Note ومرفقات الـ PO.
- ✅ المهمة اتقفلت.
- ✅ على الـ PO: Billed Qty = 2، والاستلام مابقاش يظهر في خانة Receipt لفاتورة تانية.
- Confirm ← القيد: مدين 212006 GRNI 14,800 + VAT In / دائن 211001 Suppliers.

## 5. تسليم العميل والفاتورة الضريبية
- زي ما هو: الفاتورة الضريبية لما تتأكد بتطلّع المولدات اللي في المخزن.
- ✅ على الفاتورة زرار **Delivery Notes** بيفتح أذون التسليم بتاعتها، وفي طباعة الفاتورة: *Delivery Note: WH/OUT/xxxx*.
- ✅ على إذن التسليم خانة **Tax Invoice**، وفي طباعة الإذن: *Tax Invoice: 4U-INV-…*.

لو أي خطوة طلعت مختلفة، ابعتولي صورة الشاشة.
