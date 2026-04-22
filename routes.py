from datetime import datetime, date
from functools import wraps
import csv
import io

from flask import Blueprint, flash, redirect, render_template, request, send_file, session, url_for
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .models import Product, Sale, SaleItem, StockMovement, Supplier, User

main_bp = Blueprint('main', __name__)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('main.login'))
        return view(*args, **kwargs)
    return wrapped


@main_bp.app_context_processor
def inject_globals():
    return {'now': datetime.utcnow()}


@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['full_name'] = user.full_name
            return redirect(url_for('main.dashboard'))
        flash('اسم المستخدم أو كلمة المرور غير صحيحين.', 'danger')
    return render_template('login.html')


@main_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.login'))


@main_bp.route('/')
@login_required
def dashboard():
    products_count = Product.query.count()
    suppliers_count = Supplier.query.count()
    stock_total = db.session.query(func.coalesce(func.sum(Product.stock_qty), 0)).scalar() or 0
    sales_total = db.session.query(func.coalesce(func.sum(Sale.total), 0)).scalar() or 0
    today = date.today()
    today_sales = db.session.query(func.coalesce(func.sum(Sale.total), 0)).filter(func.date(Sale.created_at) == today).scalar() or 0
    low_stock = Product.query.filter(Product.stock_qty <= Product.min_stock).order_by(Product.stock_qty.asc()).limit(8).all()
    estimated_profit = db.session.query(
        func.coalesce(func.sum((SaleItem.unit_price - Product.cost_price) * SaleItem.quantity), 0)
    ).join(Product, Product.id == SaleItem.product_id).scalar() or 0
    top_product = db.session.query(
        Product.name,
        func.coalesce(func.sum(SaleItem.quantity), 0).label('sold_qty')
    ).join(SaleItem, SaleItem.product_id == Product.id, isouter=True).group_by(Product.id).order_by(func.sum(SaleItem.quantity).desc()).first()
    recent_sales = Sale.query.order_by(Sale.created_at.desc()).limit(6).all()
    return render_template(
        'dashboard.html',
        products_count=products_count,
        suppliers_count=suppliers_count,
        stock_total=stock_total,
        sales_total=sales_total,
        today_sales=today_sales,
        estimated_profit=estimated_profit,
        low_stock=low_stock,
        top_product=top_product,
        recent_sales=recent_sales,
    )


@main_bp.route('/products', methods=['GET', 'POST'])
@login_required
def products():
    suppliers = Supplier.query.order_by(Supplier.name.asc()).all()
    if request.method == 'POST':
        sku = request.form.get('sku', '').strip()
        if Product.query.filter_by(sku=sku).first():
            flash('رمز SKU مستخدم مسبقًا.', 'danger')
            return redirect(url_for('main.products'))
        product = Product(
            sku=sku,
            name=request.form.get('name', '').strip(),
            category=request.form.get('category', '').strip(),
            size=request.form.get('size', '').strip(),
            color=request.form.get('color', '').strip(),
            brand=request.form.get('brand', '').strip(),
            cost_price=float(request.form.get('cost_price') or 0),
            sale_price=float(request.form.get('sale_price') or 0),
            stock_qty=int(request.form.get('stock_qty') or 0),
            min_stock=int(request.form.get('min_stock') or 5),
            barcode=request.form.get('barcode', '').strip(),
            description=request.form.get('description', '').strip(),
        )
        supplier_ids = request.form.getlist('supplier_ids')
        if supplier_ids:
            product.suppliers = Supplier.query.filter(Supplier.id.in_(supplier_ids)).all()
        db.session.add(product)
        db.session.flush()
        if product.stock_qty > 0:
            db.session.add(StockMovement(product_id=product.id, movement_type='in', quantity=product.stock_qty, note='رصيد افتتاحي'))
        db.session.commit()
        flash('تمت إضافة المنتج بنجاح.', 'success')
        return redirect(url_for('main.products'))

    search = request.args.get('q', '').strip()
    query = Product.query.order_by(Product.created_at.desc())
    if search:
        pattern = f'%{search}%'
        query = query.filter(
            db.or_(
                Product.name.ilike(pattern),
                Product.sku.ilike(pattern),
                Product.category.ilike(pattern),
                Product.color.ilike(pattern),
            )
        )
    products = query.all()
    return render_template('products.html', products=products, suppliers=suppliers, search=search)


@main_bp.route('/products/<int:product_id>/edit', methods=['POST'])
@login_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    old_qty = product.stock_qty
    product.name = request.form.get('name', '').strip()
    product.category = request.form.get('category', '').strip()
    product.size = request.form.get('size', '').strip()
    product.color = request.form.get('color', '').strip()
    product.brand = request.form.get('brand', '').strip()
    product.cost_price = float(request.form.get('cost_price') or 0)
    product.sale_price = float(request.form.get('sale_price') or 0)
    product.stock_qty = int(request.form.get('stock_qty') or 0)
    product.min_stock = int(request.form.get('min_stock') or 5)
    product.barcode = request.form.get('barcode', '').strip()
    product.description = request.form.get('description', '').strip()
    supplier_ids = request.form.getlist('supplier_ids')
    product.suppliers = Supplier.query.filter(Supplier.id.in_(supplier_ids)).all() if supplier_ids else []
    diff = product.stock_qty - old_qty
    if diff != 0:
        db.session.add(StockMovement(product_id=product.id, movement_type='adjustment', quantity=diff, note='تعديل من صفحة المنتجات'))
    db.session.commit()
    flash('تم تحديث المنتج.', 'success')
    return redirect(url_for('main.products'))


@main_bp.route('/products/<int:product_id>/delete', methods=['POST'])
@login_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash('تم حذف المنتج.', 'success')
    return redirect(url_for('main.products'))


@main_bp.route('/suppliers', methods=['GET', 'POST'])
@login_required
def suppliers():
    if request.method == 'POST':
        supplier = Supplier(
            name=request.form.get('name', '').strip(),
            contact_name=request.form.get('contact_name', '').strip(),
            phone=request.form.get('phone', '').strip(),
            email=request.form.get('email', '').strip(),
            address=request.form.get('address', '').strip(),
            notes=request.form.get('notes', '').strip(),
        )
        db.session.add(supplier)
        db.session.commit()
        flash('تمت إضافة المورد.', 'success')
        return redirect(url_for('main.suppliers'))
    suppliers = Supplier.query.order_by(Supplier.created_at.desc()).all()
    return render_template('suppliers.html', suppliers=suppliers)


@main_bp.route('/suppliers/<int:supplier_id>/edit', methods=['POST'])
@login_required
def edit_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    supplier.name = request.form.get('name', '').strip()
    supplier.contact_name = request.form.get('contact_name', '').strip()
    supplier.phone = request.form.get('phone', '').strip()
    supplier.email = request.form.get('email', '').strip()
    supplier.address = request.form.get('address', '').strip()
    supplier.notes = request.form.get('notes', '').strip()
    db.session.commit()
    flash('تم تحديث المورد.', 'success')
    return redirect(url_for('main.suppliers'))


@main_bp.route('/inventory', methods=['GET', 'POST'])
@login_required
def inventory():
    products = Product.query.order_by(Product.name.asc()).all()
    if request.method == 'POST':
        product_id = int(request.form.get('product_id'))
        movement_type = request.form.get('movement_type')
        quantity = int(request.form.get('quantity') or 0)
        note = request.form.get('note', '').strip()
        product = Product.query.get_or_404(product_id)

        if quantity <= 0 and movement_type in ('in', 'out'):
            flash('الكمية يجب أن تكون أكبر من صفر.', 'danger')
            return redirect(url_for('main.inventory'))

        movement_qty = quantity
        if movement_type == 'in':
            product.stock_qty += quantity
        elif movement_type == 'out':
            if product.stock_qty < quantity:
                flash('المخزون لا يكفي لهذه الحركة.', 'danger')
                return redirect(url_for('main.inventory'))
            product.stock_qty -= quantity
            movement_qty = -quantity
        else:
            product.stock_qty += quantity

        db.session.add(StockMovement(product_id=product.id, movement_type=movement_type, quantity=movement_qty, note=note))
        db.session.commit()
        flash('تم حفظ حركة المخزون.', 'success')
        return redirect(url_for('main.inventory'))

    movements = StockMovement.query.order_by(StockMovement.created_at.desc()).limit(50).all()
    return render_template('inventory.html', products=products, movements=movements)


@main_bp.route('/sales', methods=['GET', 'POST'])
@login_required
def sales():
    products = Product.query.order_by(Product.name.asc()).all()
    if request.method == 'POST':
        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')
        prices = request.form.getlist('unit_price[]')
        customer_name = request.form.get('customer_name', '').strip()
        payment_method = request.form.get('payment_method', 'cash')
        discount = float(request.form.get('discount') or 0)
        note = request.form.get('note', '').strip()

        sale = Sale(customer_name=customer_name, payment_method=payment_method, discount=discount, note=note)
        subtotal = 0
        items = []

        for product_id, qty_raw, price_raw in zip(product_ids, quantities, prices):
            if not product_id or not qty_raw:
                continue
            product = Product.query.get_or_404(int(product_id))
            qty = int(qty_raw)
            if qty <= 0:
                continue
            unit_price = float(price_raw or product.sale_price)
            if product.stock_qty < qty:
                flash(f'المخزون غير كافٍ للمنتج: {product.name}', 'danger')
                return redirect(url_for('main.sales'))
            line_total = qty * unit_price
            subtotal += line_total
            items.append((product, qty, unit_price, line_total))

        if not items:
            flash('أضف منتجًا واحدًا على الأقل.', 'danger')
            return redirect(url_for('main.sales'))

        sale.subtotal = subtotal
        sale.total = max(subtotal - discount, 0)
        db.session.add(sale)
        db.session.flush()

        for product, qty, unit_price, line_total in items:
            product.stock_qty -= qty
            db.session.add(SaleItem(sale_id=sale.id, product_id=product.id, quantity=qty, unit_price=unit_price, line_total=line_total))
            db.session.add(StockMovement(product_id=product.id, movement_type='out', quantity=-qty, note=f'فاتورة بيع #{sale.id}'))

        db.session.commit()
        flash(f'تم حفظ الفاتورة رقم {sale.id}.', 'success')
        return redirect(url_for('main.sales'))

    sales = Sale.query.order_by(Sale.created_at.desc()).limit(20).all()
    return render_template('sales.html', products=products, sales=sales)


@main_bp.route('/reports')
@login_required
def reports():
    sales = Sale.query.order_by(Sale.created_at.desc()).all()
    total_revenue = sum(s.total for s in sales)
    total_discount = sum(s.discount for s in sales)
    total_profit = db.session.query(
        func.coalesce(func.sum((SaleItem.unit_price - Product.cost_price) * SaleItem.quantity), 0)
    ).join(Product, Product.id == SaleItem.product_id).scalar() or 0
    best_sellers = db.session.query(
        Product.name,
        func.sum(SaleItem.quantity).label('total_qty')
    ).join(SaleItem, Product.id == SaleItem.product_id).group_by(Product.id).order_by(func.sum(SaleItem.quantity).desc()).limit(10).all()
    return render_template('reports.html', sales=sales, total_revenue=total_revenue, total_discount=total_discount, total_profit=total_profit, best_sellers=best_sellers)


@main_bp.route('/reports/export-sales')
@login_required
def export_sales():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Sale ID', 'Customer', 'Payment Method', 'Subtotal', 'Discount', 'Total', 'Note', 'Created At'])
    for sale in Sale.query.order_by(Sale.created_at.desc()).all():
        writer.writerow([sale.id, sale.customer_name, sale.payment_method, sale.subtotal, sale.discount, sale.total, sale.note, sale.created_at.strftime('%Y-%m-%d %H:%M')])
    mem = io.BytesIO()
    mem.write(output.getvalue().encode('utf-8-sig'))
    mem.seek(0)
    return send_file(mem, as_attachment=True, download_name='four_harts_sales.csv', mimetype='text/csv')


@main_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    user = User.query.get_or_404(session['user_id'])
    if request.method == 'POST':
        user.full_name = request.form.get('full_name', '').strip() or user.full_name
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        if new_password:
            if not check_password_hash(user.password_hash, current_password):
                flash('كلمة المرور الحالية غير صحيحة.', 'danger')
                return redirect(url_for('main.settings'))
            user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        session['full_name'] = user.full_name
        flash('تم حفظ الإعدادات.', 'success')
        return redirect(url_for('main.settings'))
    return render_template('settings.html', user=user)
