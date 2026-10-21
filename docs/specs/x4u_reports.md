# Spec — `x4u_reports`: الـ letterhead، عرض السعر زي الـ datasheet، الـ Pro-forma والفاتورة — v0.1 DRAFT

- الحالة: **مسودة للمراجعة**. مفيش كود قبل موافقتك.
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
