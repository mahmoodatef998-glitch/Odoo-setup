# Spec — `x4u_reports`: الـ letterhead، عرض السعر زي الـ datasheet، الـ Pro-forma والفاتورة — v0.2

- الحالة: **§2 الـ letterhead ✅ اتنفّذ** (2026-11-28، المستخدم: "طبق الليترهيد دا علي كل فورم بيطلع من عندنا بشكل منظم واحترافي جدا لاقصي درجه" مع `4U NEW LETTER HEAD.pdf`). باقي الأقسام زي ما هي.
- المرجع: [docs/modules/01-sales.md](../modules/01-sales.md) (D5، D7)، blueprint M5، والـ letterhead والـ datasheet اللي اتبعتوا (2026-10-21).
- يعتمد على: [`x4u_generator` datasheet](x4u_generator_datasheet.md) (البيانات) و [`x4u_sale`](x4u_sale.md) (رقم الـ Rev والـ LPO).
- العلامات: ✅ متفق عليه · 🟡 اقتراح مستني موافقتك

---

## 1. الهدف
كل المستندات اللي بتطلع للعميل على **نفس الـ letterhead بتاع 4U**، وعرض السعر فيه صفحة مواصفات لكل مولد **بنفس شكل datasheet الموقع**، والبيانات بتيجي لوحدها من الموديل والـ variant اللي اتباع.

## 2. الـ letterhead (لكل المستندات)
| الجزء | المحتوى | منين |
|---|---|---|
| Header شمال | 4U POWER GENERATION (FZC) + POWER GENERATION EQUIPMENT TRADING | اسم الشركة + سطر النشاط (حقل جديد على الشركة) |
| Header في النص | اللوجو | لوجو الشركة |
| Header يمين | الاسم بالعربي + النشاط بالعربي | حقلين جداد على الشركة |
| سطر التواصل | Tel، Mob، E-mail (`info@4upowers.com`)، العنوان، TRN | حقول الشركة: Phone، Mobile، Email، Address، Tax ID |
| خط أصفر | تحت الـ header وفوق الـ footer | ثابت في التصميم |
| Footer | شريط الماركات (Baudouin، Perkins، Leroy-Somer، Stamford، Cummins، DSE) | صورة على الشركة |

### اللي اتنفّذ (v0.2، الموديول `x4u_reports` 18.0.1.0.0)
- **Document layout اسمه "4U Letterhead"** (Settings › Companies › Configure Document Layout) على شركة 4U، فكل مستند بيتطبع بـ `web.external_layout` بياخده لوحده: Quotation / Order، PRO-FORMA، PI، Tax Invoice، Credit Note، Vendor Bill، Payment Receipt، PO، RFQ، Purchase Request، Delivery Slip، Return Slip، Count Sheet، Statements، Payslip، Cost Sheet، Check Deposit. والـ Quotation (4U) على نفس الـ layout.
- **الـ header HTML مش صورة**: الـ PDF اللي اتبعت صورة JPEG واحدة 96 DPI (هتطلع باهتة في الطباعة)، فالأسماء والـ contact line بقوا نص (Helvetica، والعربي Tajawal اللي جاي مع Odoo) واضح في أي تكبير، واللوجو من `4u-logo-hq.png` (شفاف، من غير سطر GENERATION (FZC)). اتصلّح "POWE R" و"الكهربائيه".
- **الـ watermark** (الترس + 4U + البرق، 11%) في نص كل صفحة ورا الكلام: جوّه الـ header لأن wkhtmltopdf بيرسم الـ header في كل صفحة (عنصر `position: fixed` في الـ article بيظهر في أول صفحة بس).
- **الـ footer**: "This is a formal document generated electronically." + رقم المستند + Page x of y، وتحتهم الماركات بين خطين أصفر.
- **شكل الجداول زي الـ Quotation (4U)**: عناوين الأعمدة capitals صغيرة، خط كحلي تحتها، سطر رمادي فاتح بين الصفوف، الـ Total كحلي بكتابة بيضا، التواريخ والمراجع بعنوان ذهبي، والعنوان (Invoice / Purchase Order...) بخط أصفر تحته.
- **Paper "4U Letterhead (A4)"**: margin_top 45، header_spacing 38 (الـ header بيبدأ 7 مم من فوق)، margin_bottom 30، الجانبين 12.
- **البيانات على الشركة** (تاب 4U Letterhead): الاسم والنشاط بالإنجليزي والعربي، الـ contact line (لو فاضية بتتبني من الـ Phone / Mobile / Email / Address / Tax ID)، اللوجو، الـ watermark، الماركات. بتتحمّل من `private/branding/` (برا الـ Git) بـ `scripts/set_letterhead.py`. شركة من غيرهم (ATA مثلًا) بتطبع بالـ layout العادي بتاع Odoo.
- اتصلّح معاه: الـ Quotation (4U) كانت بتقع لو السطر عليه VAT (`'%g%'` في الـ template، x4u_job_order 1.28)، وتفاصيل الـ PI بقت في سطر واحد (x4u_sale 2.5.1).
- 🟡 شريط الماركات جاي من صورة 783 px (زي اللي في الـ PDF)؛ لو في نسخة عالية الجودة (PNG / SVG) من اللوجوهات بيبقى أوضح في الطباعة.

- **مفيش بيانات حقيقية في الكود**: الكود بيقرا من حقول الشركة. إنت بتكتبها في Settings › Companies، واللوجو وشريط الماركات بيترفعوا من `private/branding/` (برا الـ Git).
- 🟡 محتاج منك **اللوجو** و**شريط الماركات** كصور PNG أو SVG بجودة عالية (اللي في الـ PDF ممكن يطلع باهت في الطباعة).

## 3. عرض السعر (Quotation)
### الصفحة الأولى: العرض
- بيانات العميل، ورقم العرض + **Rev** (مثلًا `4U-SO-012 Rev 2`)، والتاريخ، والصلاحية، والمندوب.
- سطور: الموديل (الكود + الوصف القصير "330 kVA Standby / 300 kVA Prime — Cummins")، النوع (Open / Canopy)، الـ Alternator، الكمية، السعر، الخصم، الـ VAT، الإجمالي.
- الخدمات (التركيب، النقل، التشغيل) لو اتضافت.
- الإجماليات، والشروط: الدفع، مدة التسليم، الضمان، الصلاحية، وIncoterm للتصدير.

### صفحة لكل مولد: Technical Data Sheet
- **نفس تصميم datasheet الموقع**: الكود كبير، كروت Standby / Prime / Engine / Voltage، والصورة، والجداول: Output ratings، Engine، Alternator، Fuel consumption، Dimensions & weight، Control & protection، والـ Notes.
- **حسب الـ variant**: الـ Alternator بيظهر بالماركة والـ frame اللي اتختاروا بس، والأبعاد والوزن بتوع النوع اللي اتختار (Open أو Canopy) بس.
- الألوان والخطوط زي الموقع: كحلي غامق + أصفر.

## 4. باقي المستندات
| المستند | المحتوى | الحالة |
|---|---|---|
| Pro-forma Invoice | زي العرض، والعنوان "PRO-FORMA INVOICE"، وفيه بيانات البنك (للـ LC والتصدير) | ✅ |
| Sales Order Confirmation | بعد التأكيد، وفيه رقم الـ LPO | 🟡 |
| Down Payment / Tax Invoice | "TAX INVOICE"، TRN بتاعنا وبتاع العميل، الـ VAT بالـ AED، رقم الـ SO والـ LPO | ✅ 🔵 المحاسب يراجع متطلبات الـ FTA |
| Delivery Note / PO | مع موديولات Inventory و Purchase | ⏳ |

## 5. اللغة
- المستندات **بالإنجليزي** (زي الواجهة)، والـ letterhead نفسه ثنائي اللغة.
- 🔵 المحاسب يأكد: الفاتورة الضريبية محتاجة عربي جنب الإنجليزي؟

## 6. الاختبار
1. عرض سعر لـ 4U-C350 Canopy + Stamford ← الصفحة الأولى + صفحة datasheet فيها Stamford frame وأبعاد الـ Canopy بس.
2. موديلين في نفس العرض ← صفحة datasheet لكل واحد.
3. Pro-forma والفاتورة على نفس الـ letterhead، وفيهم TRN والـ LPO.
4. تغيير بيانات الشركة (التليفون مثلًا) ← بيظهر في كل المستندات من غير كود.
5. مقارنة بالشكل معاك: الـ PDF جنب datasheet الموقع.

## 7. أسئلة
1. اللوجو وشريط الماركات كصور بجودة عالية؟
2. بيانات البنك اللي تظهر على الـ Pro-forma (إنت تكتبها في Odoo بنفسك).
3. الشروط والأحكام: نفس فقرات قالب "Generator Supply"، ولا عندكم صفحة Terms & Conditions جاهزة؟
4. 🔵 للمحاسب: العربي على الفاتورة الضريبية.
