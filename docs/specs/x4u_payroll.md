# Spec — `x4u_payroll`: المرتبات في الإمارات — v0.1

- الحالة: **اتوافق عليها 2026-11-07** (المستخدم اختار الاقتراح في الأسئلة التلاتة). اتنفّذت في `x4u_payroll` 18.0.1.0.0، على OCA `payroll` و `payroll_account` و `payroll_contract_advantages`. ده بيقفل **H3** من مراجعة الحسابات ([x4u_account](x4u_account.md)).
- العلامات: ✅ متفق عليه · 🔵 مستني المحاسب

## 1. قبل كده
OCA Payroll كان متسطّب **فاضي**: مفيش Structure، ولا قواعد، ولا فئات، ومفيش موظف عنده عقد.

## 2. هيكل المرتب "4U UAE Salary"
| القاعدة | الحساب | الحساب المحاسبي |
|---|---|---|
| Basic Salary | راتب العقد (Wage) | مدين 400003 Basic Salary |
| Housing Allowance | من العقد (Advantages › HOUSING) | مدين 400004 |
| Transportation Allowance | من العقد (TRANSPORT) | مدين 400005 |
| Other Allowance | من العقد (OTHER_ALW) | مدين 400012 Staff Other Allowances |
| Gross | Basic + البدلات | — |
| Unpaid Days | Input `ABSENCE_DAYS`: Gross / 30 × الأيام (سالب) | بيقلّل 400003 |
| Advance / Loan Recovery | Input `ADVANCE` (سالب) | دائن **102016 Staff Advances & Loans** (جديد) |
| **Net Salary** | Basic + البدلات + الخصومات | دائن **201004 Accrued - Salaries** |

- الـ Net بيفضل في 201004 لحد ما البنك يدفع (WPS): مدين 201004 / دائن Bank.
- السلفة نفسها لما تتدفع للموظف: مدين 102016 / دائن Bank أو Petty Cash.
- journal جديد **SAL Salaries**، وبيتحط لوحده على أي عقد جديد، ومعاه الـ Structure.

## 3. مخصصات الشركة (كل شهر، ومش بتظهر على قسيمة المرتب)
| المخصص | الحساب | القيد |
|---|---|---|
| **End of Service** | Basic / 30 × **21 يوم** في السنة لأول 5 سنين، و **30 يوم** بعدها ÷ 12 (قانون العمل 2021) | مدين 400008 / دائن 202001 End of Service Provision |
| **Leave Salary** | 30 يوم في السنة على **الـ Basic بس**: Basic ÷ 12 | مدين 400007 / دائن 201006 Leave Days Provision |
| **Air Ticket** | المبلغ السنوي على العقد (AIR_TICKET) ÷ 12 | مدين 400006 / دائن 201005 Leave Tickets Provision |

- مدة الخدمة من `service_start_date` بتاع الموظف (OCA `hr_employee_service`)، ولو مش موجود من بداية العقد.
- مثال (التيست): Basic 6,000، Housing 3,000، Transport 500، تذكرة 2,400 في السنة، خدمة سنتين، يومين غياب، سلفة 1,000 ← Gross 9,500، الغياب ‎-633.33، الـ Net 7,866.67. المخصصات: End of Service 350، و Leave 500، و Ticket 200. وبعد 5 سنين، الـ End of Service = 500.

## 4. 🔵 للمحاسب
1. **سقف End of Service** (مرتب سنتين) والموظفين اللي أقل من سنة (مالهمش مكافأة لو مشيوا): المخصص بيتحسب من أول يوم (IAS 19)، والمحاسب بيعمل تسوية آخر السنة على المستحق الفعلي.
2. الإجازة اللي اتاخدت بتتصرف من 201006، مش مصروف جديد.
3. **ملف WPS (SIF)** للبنك: مش في OCA، ومحتاج spec لوحده بعد ما نعرف البنك.
4. لو فيه شركة تانية (ATA)، القواعد محتاجة نسخة بحساباتها.
