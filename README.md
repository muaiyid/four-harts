# Four Harts Pro Mobile Ready

نظام Four Harts الاحترافي، مهيأ للهاتف ومجهز للنشر على الإنترنت.

## أهم المزايا
- تسجيل دخول خاص بمدير واحد فقط
- قاعدة بيانات SQLite حقيقية
- إدارة المنتجات والمخزون والمبيعات
- إدارة الموردين وربط عدة موردين بكل منتج
- تصميم متجاوب مناسب للجوال
- ملفات نشر جاهزة لـ Render أو أي استضافة Python مشابهة

## التشغيل محليًا
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
ثم افتح:
`http://127.0.0.1:5000`

## بيانات الدخول الافتراضية
- username: `admin`
- password: `admin123`

## للنشر على Render
1. ارفع المشروع إلى GitHub.
2. أنشئ خدمة Web Service جديدة على Render.
3. اجعل أمر البناء:
   `pip install -r requirements.txt`
4. واجعل أمر التشغيل:
   `gunicorn app:app`
5. أضف متغيرات البيئة التالية:
   - `SECRET_KEY`
   - `ADMIN_PASSWORD`
   - `DATABASE_PATH`
6. بعد النشر ستحصل على رابط مباشر يفتح من الهاتف.

## مهم
SQLite مناسبة كبداية ممتازة لمستخدم واحد. إذا أردت لاحقًا نسخة أونلاين أقوى جدًا، يمكن نقلها إلى PostgreSQL بسهولة.
