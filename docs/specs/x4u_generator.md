# Spec — `x4u_generator` (Generator Card) — v1.0 APPROVED

- الحالة: **اتوافق عليه** 2026-10-17. اقتراحات Q1–Q6 اتوافق عليها زي ما هي (راجع آخر جدول).
- التاريخ: 2026-10-17 — Odoo 18.0 Community، DB `odoo4u_dev` (3 demo companies).

---

## 1. الهدف
كل مولد (genset) له Serial No بيبقى له **كارت واحد** يجمع:
مواصفاته (KVA، ماركة وموديل الـ Engine والـ Alternator) ← مين اشتراه (Sales Order + Customer + تاريخ التسليم) ← ساعات التشغيل ← الضمان ← نتيجة Quality Inspection.

## 2. قرارات التصميم
| # | القرار | السبب |
|---|---|---|
| D1 | موديل جديد `x4u.generator` مربوط **1:1** بـ `stock.lot` (مش fields على `stock.lot` نفسه). | الكارت له دورة حياة بعد البيع (قراءات، ضمان، وبعدين صيانة وclaims). ومش عايزين نحط حقول مولدات على كل lots قطع الغيار. نفس فكرة `maintenance.equipment` في Odoo. |
| D2 | المواصفات الثابتة للموديل (KVA، الماركات، مدة الضمان) تتسجل مرة واحدة على `product.template`، وتتنسخ للكارت وقت إنشائه، وتفضل قابلة للتعديل على الكارت. | لو في التجميع اتغيّر alternator لوحدة معيّنة نقدر نسجّل الحقيقة. |
| D3 | الكارت يتعمل **أوتوماتيك** أول ما يتعمل Lot/Serial لمنتج عليه `Is Generator`، أياً كان المصدر (Receipt أو Manufacturing Order أو يدوي). | مفيش مولد من غير كارت. |
| D4 | بيانات البيع والجودة **تتقري** من Odoo/OCA (`sale_stock`, `quality_control_stock_oca`)، وما بنكررهاش. | مصدر واحد للحقيقة. |
| D5 | مفيش Security Groups جديدة في v1، بنستخدم groups الـ Inventory / Sales / Quality الموجودة. | أبسط في الإدارة. |

## 3. Manifest
- `name`: 4U Generator Card — `version`: `18.0.1.0.0` — `license`: **AGPL-3** (Q1)
- `depends`: `stock`, `sale_stock`, `quality_control_stock_oca`
  (`mrp` مش dependency. الـ MO اللي بيعمل serial هيعمل الكارت تلقائي من D3.)

## 4. Models

### 4.1 `x4u.generator` — Generator Card  (`mail.thread`, `mail.activity.mixin`)
| Field | Type | القاعدة / المصدر |
|---|---|---|
| `name` | Char, related `lot_id.name`, stored | **Serial No** (هو نفسه رقم الـ Lot/Serial) |
| `lot_id` | M2o `stock.lot`, required, **unique**, `ondelete=restrict` | |
| `product_id` | related `lot_id.product_id`, stored | |
| `company_id` | M2o `res.company`, required | شركة الـ Lot، ولو الـ Lot من غير شركة تبقى الشركة الحالية. (تعديل وقت التنفيذ: في Odoo 18 الـ Lot بتاع منتج مشترك بين الشركات بيبقى من غير شركة، فالـ related كان بيكسر الـ multi-company.) |
| `kva_prime` | Float, required | default من المنتج |
| `kva_standby` | Float | default من المنتج (Q4) |
| `engine_brand_id` | M2o `x4u.generator.brand` (type engine) | default من المنتج |
| `engine_model` | Char | default من المنتج |
| `engine_serial` | Char | رقم المحرك من المصنّع، ومهم لـ warranty claims |
| `alternator_brand_id` | M2o `x4u.generator.brand` (type alternator) | default من المنتج |
| `alternator_model` | Char | default من المنتج |
| `alternator_serial` | Char | |
| `state` | Selection: `in_stock` / `delivered` / `commissioned` | يتحدّث تلقائي (R4–R6) |
| `customer_id` | M2o `res.partner` | الـ commercial partner بتاع الـ delivery |
| `site_address_id` | M2o `res.partner` | عنوان التسليم/الموقع (`picking.partner_id`) |
| `sale_order_id` | M2o `sale.order` | من `move.sale_line_id.order_id` |
| `delivery_picking_id` | M2o `stock.picking` | |
| `delivery_date` | Date | `picking.date_done` |
| `commissioning_date` | Date | يدوي: تاريخ التشغيل عند العميل |
| `hour_reading_ids` | O2m `x4u.generator.hour.reading` | |
| `running_hours` | Float, computed, stored | آخر قراءة حسب التاريخ |
| `last_reading_date` | Datetime, computed, stored | |
| `warranty_months` | Integer | default من المنتج |
| `warranty_hours` | Float | default من المنتج (0 = مفيش حد ساعات) |
| `warranty_start_date` | Date, computed, stored, `readonly=False` | R8 / Q2 |
| `warranty_end_date` | Date, computed, stored | start + months |
| `warranty_state` | Selection: `not_started` / `active` / `expired` | R8 + daily cron |
| `qc_inspection_ids` | related `lot_id.qc_inspections_ids` | من `quality_control_stock_oca` |
| `qc_state` | Selection: `none` / `pending` / `passed` / `failed`, computed, stored | R9 |
| `note` | Html | |
| `active` | Boolean | Archive بدل الحذف |

`tracking=True` على: state، customer، sale order، commissioning/warranty dates، والـ serials.

### 4.2 `x4u.generator.hour.reading` — Running Hours Reading
| Field | Type | |
|---|---|---|
| `generator_id` | M2o, required, `ondelete=cascade` | |
| `date` | Datetime, required, default now | |
| `hours` | Float, required | R7 |
| `source` | Selection: `factory_test` / `commissioning` / `service` / `customer` / `other` | |
| `user_id` | M2o `res.users`, default current user | |
| `note` | Char | |
| `company_id` | related `generator_id.company_id`, stored | للـ record rule |

### 4.3 `x4u.generator.brand` — Engine / Alternator Brand
| Field | Type | |
|---|---|---|
| `name` | Char, required, unique | مثال: Perkins, Cummins, Stamford, Leroy-Somer |
| `brand_type` | Selection: `engine` / `alternator` / `both` | |
| `active` | Boolean | |

مشترك بين كل الشركات (من غير `company_id`).

### 4.4 Extensions على موديلات موجودة (prefix `x4u_`)
| Model | الإضافة |
|---|---|
| `product.template` | `x4u_is_generator`, `x4u_kva_prime`, `x4u_kva_standby`, `x4u_engine_brand_id`, `x4u_engine_model`, `x4u_alternator_brand_id`, `x4u_alternator_model`, `x4u_warranty_months` (default Q6), `x4u_warranty_hours`. وتاب **Generator** في الـ product form يظهر بس لو `x4u_is_generator`. |
| `stock.lot` | `x4u_generator_ids` (O2m) + `x4u_generator_id` (computed) + smart button **Generator Card** + زرار **Create Generator Card** للـ lots القديمة. |
| `stock.picking` | logic بس (R4/R5)، override لـ `_action_done` بعد `super()`. |
| `sale.order` | `x4u_generator_count` + smart button **Generators**. |
| `res.partner` | `x4u_generator_count` + smart button **Generators** (الـ installed base عند العميل). |

## 5. Business Rules
| # | القاعدة |
|---|---|
| R1 | منتج عليه `x4u_is_generator` لازم يكون `tracking = serial` و `is_storable`، وإلا يطلع `ValidationError`. |
| R2 | لو اتعمل `stock.lot` لمنتج generator، يتعمل كارت تلقائي والمواصفات تتنسخ من المنتج. لو المنتج مش generator مفيش حاجة تحصل. |
| R3 | كارت واحد بس لكل lot (SQL unique على `lot_id`). |
| R4 | لما outgoing picking رايح `location_dest_id.usage = customer` وفيه serial مولد يتعمله Validate، الكارت ياخد: customer, site address, sale order, picking, delivery date، والـ `state = delivered`، ويتسجل message في الـ chatter. |
| R5 | لما return من الـ customer location يتعمله Validate: `state = in_stock`، وحقول العميل والـ SO تتمسح (القيم القديمة محفوظة في الـ tracking/chatter). |
| R6 | لما يتحط `commissioning_date`: الـ `state = commissioned`. مسموح بس لو المولد delivered، والتاريخ ماينفعش يبقى قبل `delivery_date`. |
| R7 | قراءة الساعات لازم ≥ 0، وماينفعش تبقى أقل من القراءة اللي قبلها بالتاريخ (العداد مايرجعش لورا). `running_hours` = آخر قراءة. |
| R8 | **Warranty:** start = `commissioning_date` ولو مش موجود يبقى `delivery_date` (راجع Q2). end = start + `warranty_months`. `expired` لو النهارده عدّى الـ end **أو** (`warranty_hours > 0` و `running_hours ≥ warranty_hours`)، أيهما أقرب. `not_started` لو مفيش start. غير كده `active`. فيه cron يومي يعيد الحساب. |
| R9 | **QC:** `qc_state` من آخر inspection (مش canceled) على الـ lot: `success` يبقى passed، `failed` يبقى failed، غير كده pending. ولو مفيش inspections يبقى none. (المنع وقت التسليم: راجع Q3.) |
| R10 | الحذف للـ Inventory Administrator بس. الطبيعي Archive. |

## 6. UI / Menus
- **Inventory › Products › Generator Cards** و **Sales › Products › Generator Cards** (read-only للمبيعات).
- **Quality Control › Inspections › Generator Cards** (read-only لفريق الجودة، اتضافت وقت التنفيذ).
- **Inventory › Configuration › Generator Brands**.
- **Form:** header فيه statusbar للـ `state`. Smart buttons: Lot, Sales Order, Delivery, Inspections (count). Tabs: Specs / Sale & Delivery / Running Hours (inline list) / Warranty / Quality / Notes. والـ Chatter.
- **List:** Serial, Product, kVA, Engine Brand, Alternator Brand, Customer, State, Running Hours, Warranty End, Warranty State, QC State. أحمر (`decoration-danger`) للـ expired و failed.
- **Search:** filters: In Stock / Delivered / Commissioned / Warranty Active / Warranty Expiring (30 days) / Warranty Expired / QC Pending / QC Failed. Group by: Product, Engine Brand, Alternator Brand, Customer, State, Company.
- Odoo 18 syntax: `<list>` و `invisible="..."`، من غير `attrs`.

## 7. Security
| Group | `x4u.generator` | `hour.reading` | `brand` |
|---|---|---|---|
| `stock.group_stock_user` (Inventory / User) | R W C | R W C | R |
| `stock.group_stock_manager` (Inventory / Administrator) | R W C D | R W C D | R W C D |
| `sales_team.group_sale_salesman` | R | R | R |
| `quality_control_oca.group_quality_control_user` | R | R | R |

> تعديل وقت التنفيذ: الـ QC user بقى R بس على الـ readings، لأن إضافة قراءة بتحصل من داخل الكارت، وده محتاج write على الكارت نفسه.

**Record rules (multi-company):** على `x4u.generator` و `x4u.generator.hour.reading`:
`['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]`.

## 8. Data
- `data/ir_cron.xml`: cron يومي **Generator: Update Warranty Status**.
- `demo/`: منتج demo «4U Genset 500 kVA (Demo)» + brands (Perkins, Cummins, Volvo Penta, Stamford, Leroy-Somer, Mecc Alte) + 2 serials. **demo بس**، مفيش بيانات حقيقية.

## 9. Tests (`tests/`, `TransactionCase`, `post_install`)
| # | الاختبار |
|---|---|
| T1 | serial لمنتج generator يعمل كارت فيه المواصفات اللي اتنسخت. serial لمنتج عادي مايعملش كارت. |
| T2 | R1: لما أعلّم منتج tracking=none إنه generator يطلع error. |
| T3 | R3: كارت تاني لنفس الـ lot يطلع error. |
| T4 | R7: `running_hours` = آخر قراءة، وقراءة أقل من اللي قبلها تطلع error. |
| T5 | R8: الـ end date صح، و expired بالوقت، و expired بالساعات قبل الوقت، والـ cron. |
| T6 | R4: SO ← confirm ← deliver serial، والكارت فيه customer و SO و delivery date و `delivered`. |
| T7 | R5: return، والكارت يرجع `in_stock`. |
| T8 | R9: inspection success/failed على الـ lot، والـ `qc_state` يتغير. |
| T9 | Multi-company: user في Company B مايشوفش كارت Company A. |
| T10 | Q3: الـ Inventory User مايقدرش يسلّم مولد QC بتاعه مش passed، والـ Inventory Admin يقدر ويتسجل ده في الـ chatter. |

التشغيل يبقى على DB مؤقتة: `--test-enable -i x4u_generator --stop-after-init`.

## 10. خارج نطاق v1 (Phase 2)
Service/Maintenance visits، Warranty claims، PDF (Generator Card / Warranty Certificate)، ترجمة عربي `i18n/ar.po`، بيانات الـ Controller (DSE/ComAp) والـ Canopy/ATS، ربط `mrp.production` على الكارت، تغيير العداد (meter replacement)، Customer portal، Import للـ installed base القديم.

## 11. القرارات (اتوافق على الاقتراح في كل الأسئلة — 2026-10-17)
| # | السؤال | القرار |
|---|---|---|
| Q1 | **License:** موديولات `quality_control_*_oca` رخصتها **AGPL-3**. وقاعدة OCA إن الموديول اللي بيعتمد على AGPL يبقى AGPL. لكن CLAUDE.md بيقول LGPL-3. | `x4u_generator` يبقى **AGPL-3**. مفيش أي تأثير لأن الاستخدام داخلي. (البديل: نقسمه لـ core LGPL + bridge `x4u_generator_quality` AGPL.) |
| Q2 | بداية الضمان: commissioning ولو مش موجود delivery؟ وهل فيه حد أقصى من تاريخ التسليم (زي «12 شهر من التشغيل أو 18 من التسليم»)؟ | commissioning ثم delivery، والحد الأقصى من التسليم يبقى field اختياري. |
| Q3 | نمنع تسليم مولد لعميل لو الـ QC مش passed؟ | **نعم، Block** على outgoing لعميل، والـ Inventory Admin بس هو اللي يقدر يتخطاه. |
| Q4 | KVA: Prime و Standby الاتنين ولا واحد بس؟ | الاتنين، والـ Prime required. |
| Q5 | المواصفات على الكارت قابلة للتعديل ولا مقفولة على المنتج؟ | قابلة للتعديل (D2). |
| Q6 | الـ default بتاع الضمان: 12 شهر / 1000 ساعة؟ | 12 شهر و 0 (يعني مفيش حد ساعات) لحد ما تحدد. |
