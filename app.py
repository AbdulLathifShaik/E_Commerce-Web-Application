import os, uuid
from functools import wraps
import mysql.connector
from dotenv import load_dotenv
from flask import Flask, request, redirect, render_template, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from otp import genotp
from cmail import sendmail
from project import encode, decode, hash_otp, otp_matches

load_dotenv()
BASE = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(BASE, 'static', 'uploads')
os.makedirs(UPLOADS, exist_ok=True)
ALLOWED = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
CATEGORIES = ['Home_appliances', 'Electronics', 'Fashion', 'Grocery']
DB = dict(host=os.getenv('DB_HOST', 'localhost'), port=int(os.getenv('DB_PORT', 3306)),
          user=os.getenv('DB_USER', 'root'), password=os.getenv('DB_PASSWORD', ''),
          database=os.getenv('DB_NAME', 'e_commerce'))
ITEM = "bin_to_uuid(item_id) id, item_name, description, quantity, price, category, image_name"

app = Flask(__name__)
app.secret_key = os.environ['SECRET_KEY']
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024


# ---------- database helpers ----------
def q(sql, args=(), one=False, commit=False):
    conn = mysql.connector.connect(**DB)
    try:
        cur = conn.cursor(dictionary=True, buffered=True)
        cur.execute(sql, args)
        if commit:
            conn.commit()
            return cur.rowcount
        return cur.fetchone() if one else cur.fetchall()
    finally:
        conn.close()


def init_db():
    with open(os.path.join(BASE, 'schema.sql'), encoding='utf-8') as f:
        statements = [s.strip() for s in f.read().split(';') if s.strip()]
    conn = mysql.connector.connect(**DB)
    cur = conn.cursor()
    for s in statements:
        cur.execute(s)
    conn.commit()
    conn.close()


init_db()


@app.errorhandler(mysql.connector.Error)
def db_error(e):
    return f'Database error: {e}', 500


@app.context_processor
def inject():
    cart = session.get('cart', {})
    return {'categories': CATEGORIES, 'cart_count': sum(c['qty'] for c in cart.values())}


# ---------- misc helpers ----------
def admin_required(f):
    @wraps(f)
    def wrapper(*a, **k):
        if not session.get('admin'):
            return redirect(url_for('adminlogin'))
        return f(*a, **k)
    return wrapper


def user_required(f):
    @wraps(f)
    def wrapper(*a, **k):
        if not session.get('user'):
            flash('Please log in to continue')
            return redirect(url_for('userlogin'))
        return f(*a, **k)
    return wrapper


def save_image(file):
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED:
        return None
    name = uuid.uuid4().hex + '.' + ext
    file.save(os.path.join(UPLOADS, name))
    return name


def remove_image(name):
    if name:
        path = os.path.join(UPLOADS, name)
        if os.path.isfile(path):
            os.remove(path)


def get_item(itemid, admin=None):
    try:
        uuid.UUID(itemid)
    except ValueError:
        return None
    sql = f'select {ITEM} from items where item_id=uuid_to_bin(%s)'
    args = [itemid]
    if admin:
        sql += ' and added_by=%s'
        args.append(admin)
    return q(sql, args, one=True)


def item_values(f):
    try:
        price, qty = float(f['price']), int(f['quantity'])
        if price < 0 or qty < 0 or f['category'] not in CATEGORIES:
            return None
    except (ValueError, KeyError):
        return None
    return [f['title'].strip(), f['description'].strip(), price, qty, f['category']]


def send_otp(email, otp, data, endpoint, param, back):
    try:
        sendmail(email, 'Ecommy verification code', f'Your verification code is {otp}. It is valid for 15 minutes.')
    except Exception as e:
        print('MAIL ERROR:', e)
        flash('Could not send the email. Check MAIL_USER and MAIL_APP_PASSWORD in .env')
        return redirect(url_for(back))
    if os.getenv('MAIL_DEBUG') == '1':
       flash(f'Test mode: your code is {otp}')
    else:
       flash('We sent a verification code to your email')
    return redirect(url_for(endpoint, **{param: encode(data)}))


def forgot(table, col, endpoint):
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        if q(f'select 1 from {table} where {col}=%s', [email], one=True):
            link = url_for(endpoint, token=encode({'e': email, 't': table}), _external=True)
            try:
                sendmail(email, 'Reset your Ecommy password', f'Open this link to set a new password:\n{link}')
            except Exception as e:
                print('MAIL ERROR:', e)
                flash('Could not send the email. Check MAIL settings in .env')
                return redirect(request.path)
        flash('If that email is registered, a reset link is on its way')
        return redirect(request.path)
    return render_template('forgot.html')


def reset(token, table, col, login):
    try:
        d = decode(token)
        if d['t'] != table:
            raise ValueError
    except Exception:
        flash('This reset link is invalid or has expired')
        return redirect(url_for(login))
    if request.method == 'POST':
        n, c = request.form['npassword'], request.form['cpassword']
        if n != c:
            flash('Passwords do not match')
        elif len(n) < 6:
            flash('Password must be at least 6 characters')
        else:
            q(f'update {table} set password=%s where {col}=%s', [generate_password_hash(n), d['e']], commit=True)
            flash('Password updated, you can log in now')
            return redirect(url_for(login))
    return render_template('newpassword.html')


# ---------- public pages ----------
@app.route('/')
def home():
    return render_template('welcome.html', items=q(f'select {ITEM} from items order by rand() limit 4'))


@app.route('/index')
def index():
    return render_template('index.html', items=q(f'select {ITEM} from items order by item_name'), heading='All products')


@app.route('/category/<type>')
def category(type):
    if type not in CATEGORIES:
        return redirect(url_for('index'))
    items = q(f'select {ITEM} from items where category=%s', [type])
    return render_template('dashboard.html', items=items, heading=type.replace('_', ' '))


@app.route('/search')
def search():
    term = request.args.get('search', '').strip()
    if not term:
        return redirect(url_for('index'))
    like = f'%{term}%'
    items = q(f'select {ITEM} from items where item_name like %s or description like %s or category like %s', [like] * 3)
    return render_template('dashboard.html', items=items, heading=f'Results for "{term}"')


@app.route('/description/<itemid>')
def description(itemid):
    item = get_item(itemid)
    if not item:
        flash('That product does not exist')
        return redirect(url_for('index'))
    reviews = q('select r.title, r.review, r.rating, r.date, u.username from reviews r '
                'join usercreate u on u.user_email=r.username where r.itemid=uuid_to_bin(%s) order by r.date desc', [itemid])
    avg = round(sum(r['rating'] for r in reviews) / len(reviews), 1) if reviews else None
    return render_template('description.html', item=item, reviews=reviews, avg=avg)


@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        f = request.form
        q('insert into contactus(name,email,message) values(%s,%s,%s)', [f['name'], f['email'], f['message']], commit=True)
        flash('Thanks, we received your message')
        return redirect(url_for('contact'))
    return render_template('contact.html')


# ---------- admin: signup, login, reset ----------
@app.route('/admincreate', methods=['GET', 'POST'])
def admincreate():
    if request.method == 'POST':
        f = request.form
        email = f['email'].strip().lower()
        if q('select 1 from admincreate where email=%s', [email], one=True):
            flash('This email is already registered, please log in')
            return redirect(url_for('adminlogin'))
        if not f.get('agree'):
            flash('Please accept the terms to continue')
            return redirect(url_for('admincreate'))
        otp = genotp()
        data = {'name': f['username'].strip(), 'email': email, 'password': generate_password_hash(f['password']),
                'address': f['address'].strip(), 'otp': hash_otp(otp)}
        return send_otp(email, otp, data, 'otp', 'paotp', 'admincreate')
    return render_template('admincreate.html')


@app.route('/otp/<paotp>', methods=['GET', 'POST'])
def otp(paotp):
    if request.method == 'POST':
        try:
            d = decode(paotp, max_age=900)
        except Exception:
            flash('The code expired, please register again')
            return redirect(url_for('admincreate'))
        if otp_matches(d['otp'], request.form['otp']):
            try:
                q('insert into admincreate(email,username,password,address,accept) values(%s,%s,%s,%s,%s)',
                  [d['email'], d['name'], d['password'], d['address'], 'on'], commit=True)
            except mysql.connector.IntegrityError:
                flash('This email is already registered')
                return redirect(url_for('adminlogin'))
            flash('Registration complete, please log in')
            return redirect(url_for('adminlogin'))
        flash('Wrong code, please try again')
    return render_template('adminotp.html')


@app.route('/adminlogin', methods=['GET', 'POST'])
def adminlogin():
    if session.get('admin'):
        return redirect(url_for('adminpanel'))
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        row = q('select password from admincreate where email=%s', [email], one=True)
        if row and check_password_hash(row['password'], request.form['password']):
            session['admin'] = email
            return redirect(url_for('adminpanel'))
        flash('Wrong email or password')
    return render_template('adminlogin.html')


@app.route('/adminforgot', methods=['GET', 'POST'])
def adminforgot():
    return forgot('admincreate', 'email', 'ad_password_update')


@app.route('/ad_password_update/<token>', methods=['GET', 'POST'])
def ad_password_update(token):
    return reset(token, 'admincreate', 'email', 'adminlogin')


@app.route('/adminlogout')
@app.route('/logout')
def adminlogout():
    session.pop('admin', None)
    return redirect(url_for('home'))


# ---------- admin: panel, profile, items ----------
@app.route('/adminpanel')
@admin_required
def adminpanel():
    me = q('select username,dp_image from admincreate where email=%s', [session['admin']], one=True)
    count = q('select count(*) c from items where added_by=%s', [session['admin']], one=True)['c']
    return render_template('adminpanel.html', me=me, count=count)


@app.route('/adminprofileupdate', methods=['GET', 'POST'])
@admin_required
def adminprofileupdate():
    me = q('select username,address,dp_image,ph_no from admincreate where email=%s', [session['admin']], one=True)
    if request.method == 'POST':
        f = request.form
        img = me['dp_image']
        phone = f.get('phone', '').strip() or None
        if phone and not phone.isdigit():
            flash('Phone number must contain digits only')
            return redirect(url_for('adminprofileupdate'))
        file = request.files.get('file')
        if file and file.filename:
            new = save_image(file)
            if not new:
                flash('Use a png, jpg, jpeg, gif or webp image')
                return redirect(url_for('adminprofileupdate'))
            remove_image(img)
            img = new
        try:
            q('update admincreate set username=%s,address=%s,ph_no=%s,dp_image=%s where email=%s',
              [f['adminname'].strip(), f['address'].strip(), phone, img, session['admin']], commit=True)
        except mysql.connector.IntegrityError:
            flash('That phone number is already used')
            return redirect(url_for('adminprofileupdate'))
        flash('Profile updated')
        return redirect(url_for('adminprofileupdate'))
    return render_template('adminupdate.html', me=me)


@app.route('/additem', methods=['GET', 'POST'])
@admin_required
def additem():
    if request.method == 'POST':
        vals = item_values(request.form)
        file = request.files.get('file')
        if not vals:
            flash('Please check the price, quantity and category')
            return redirect(url_for('additem'))
        name = save_image(file) if file and file.filename else None
        if not name:
            flash('Upload a png, jpg, jpeg, gif or webp image')
            return redirect(url_for('additem'))
        q('insert into items(item_id,item_name,description,price,quantity,category,image_name,added_by) '
          'values(uuid_to_bin(uuid()),%s,%s,%s,%s,%s,%s,%s)', vals + [name, session['admin']], commit=True)
        flash(f'{vals[0]} added')
        return redirect(url_for('additem'))
    return render_template('additem.html', item=None)


@app.route('/viewallitems')
@admin_required
def viewallitems():
    items = q(f'select {ITEM} from items where added_by=%s order by item_name', [session['admin']])
    return render_template('viewall_items.html', items=items)


@app.route('/viewitem/<item_id>')
@admin_required
def viewitem(item_id):
    item = get_item(item_id, session['admin'])
    if not item:
        flash('Item not found')
        return redirect(url_for('viewallitems'))
    return render_template('view_item.html', item=item)


@app.route('/updateitem/<item_id>', methods=['GET', 'POST'])
@admin_required
def updateitem(item_id):
    item = get_item(item_id, session['admin'])
    if not item:
        flash('Item not found')
        return redirect(url_for('viewallitems'))
    if request.method == 'POST':
        vals = item_values(request.form)
        if not vals:
            flash('Please check the price, quantity and category')
            return redirect(url_for('updateitem', item_id=item_id))
        img = item['image_name']
        file = request.files.get('file')
        if file and file.filename:
            new = save_image(file)
            if not new:
                flash('Upload a png, jpg, jpeg, gif or webp image')
                return redirect(url_for('updateitem', item_id=item_id))
            remove_image(img)
            img = new
        q('update items set item_name=%s,description=%s,price=%s,quantity=%s,category=%s,image_name=%s '
          'where item_id=uuid_to_bin(%s) and added_by=%s', vals + [img, item_id, session['admin']], commit=True)
        flash('Item updated')
        return redirect(url_for('viewitem', item_id=item_id))
    return render_template('update_item.html', item=item)


@app.route('/deleteitem/<item_id>', methods=['POST'])
@admin_required
def deleteitem(item_id):
    item = get_item(item_id, session['admin'])
    if item:
        q('delete from items where item_id=uuid_to_bin(%s)', [item_id], commit=True)
        remove_image(item['image_name'])
        flash('Item deleted')
    return redirect(url_for('viewallitems'))


# ---------- user: signup, login, reset ----------
@app.route('/usersignup', methods=['GET', 'POST'])
def usersignup():
    if request.method == 'POST':
        f = request.form
        email = f['email'].strip().lower()
        if q('select 1 from usercreate where user_email=%s or username=%s', [email, f['username'].strip()], one=True):
            flash('That email or username is already registered')
            return redirect(url_for('userlogin'))
        otp = genotp()
        data = {'name': f['username'].strip(), 'email': email, 'password': generate_password_hash(f['password']),
                'address': f['address'].strip(), 'gender': f.get('gender') or None, 'otp': hash_otp(otp)}
        return send_otp(email, otp, data, 'ootp', 'passotp', 'usersignup')
    return render_template('usersignup.html')


@app.route('/ootp/<passotp>', methods=['GET', 'POST'])
def ootp(passotp):
    if request.method == 'POST':
        try:
            d = decode(passotp, max_age=900)
        except Exception:
            flash('The code expired, please sign up again')
            return redirect(url_for('usersignup'))
        if otp_matches(d['otp'], request.form['otp']):
            gender = d['gender'] if d['gender'] in ('Male', 'Female') else None
            try:
                q('insert into usercreate(username,user_email,password,address,gender) values(%s,%s,%s,%s,%s)',
                  [d['name'], d['email'], d['password'], d['address'], gender], commit=True)
            except mysql.connector.IntegrityError:
                flash('That email or username is already registered')
                return redirect(url_for('userlogin'))
            flash('Registration complete, please log in')
            return redirect(url_for('userlogin'))
        flash('Wrong code, please try again')
    return render_template('userotp.html')


@app.route('/userlogin', methods=['GET', 'POST'])
def userlogin():
    if session.get('user'):
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        row = q('select password from usercreate where user_email=%s', [email], one=True)
        if row and check_password_hash(row['password'], request.form['password']):
            session['user'] = email
            return redirect(url_for('index'))
        flash('Wrong email or password')
    return render_template('userlogin.html')


@app.route('/userforgot', methods=['GET', 'POST'])
def userforgot():
    return forgot('usercreate', 'user_email', 'user_password_update')


@app.route('/user_password_update/<token>', methods=['GET', 'POST'])
def user_password_update(token):
    return reset(token, 'usercreate', 'user_email', 'userlogin')


@app.route('/userlogout')
def userlogout():
    session.pop('user', None)
    session.pop('cart', None)
    return redirect(url_for('index'))


# ---------- user: cart, orders, reviews ----------
@app.route('/addcart/<itemid>')
@user_required
def addcart(itemid):
    item = get_item(itemid)
    back = request.referrer or url_for('index')
    if not item:
        flash('That product does not exist')
        return redirect(url_for('index'))
    cart = session.get('cart', {})
    have = cart.get(itemid, {}).get('qty', 0)
    if have + 1 > (item['quantity'] or 0):
        flash('No more stock available for this product')
        return redirect(back)
    cart[itemid] = {'name': item['item_name'], 'price': float(item['price']), 'qty': have + 1, 'image': item['image_name']}
    session['cart'] = cart
    flash(f"{item['item_name']} added to your cart")
    return redirect(back)


@app.route('/viewcart')
@user_required
def viewcart():
    cart = session.get('cart', {})
    total = sum(c['price'] * c['qty'] for c in cart.values())
    return render_template('cart.html', cart=cart, total=total)


@app.route('/removecart_item/<itemid>')
@user_required
def removecart_item(itemid):
    cart = session.get('cart', {})
    cart.pop(itemid, None)
    session['cart'] = cart
    flash('Item removed from your cart')
    return redirect(url_for('viewcart'))


@app.route('/checkout', methods=['POST'])
@user_required
def checkout():
    cart = session.get('cart', {})
    if not cart:
        return redirect(url_for('viewcart'))
    conn = mysql.connector.connect(**DB)
    try:
        cur = conn.cursor()
        for itemid, c in cart.items():
            cur.execute('update items set quantity=quantity-%s where item_id=uuid_to_bin(%s) and quantity>=%s',
                        [c['qty'], itemid, c['qty']])
            if cur.rowcount == 0:
                raise ValueError(c['name'])
            cur.execute('insert into orders(itemid,item_name,qty,total_price,user) '
                        'select item_id,item_name,%s,price*%s,%s from items where item_id=uuid_to_bin(%s)',
                        [c['qty'], c['qty'], session['user'], itemid])
        conn.commit()
    except ValueError as e:
        conn.rollback()
        flash(f'Not enough stock left for {e}')
        return redirect(url_for('viewcart'))
    finally:
        conn.close()
    session.pop('cart', None)
    flash('Order placed. Thank you!')
    return redirect(url_for('orders'))


@app.route('/orders')
@user_required
def orders():
    rows = q('select orderid,item_name,qty,total_price,ordered_at from orders where user=%s order by orderid desc', [session['user']])
    return render_template('orders.html', orders=rows)


@app.route('/addreview/<itemid>', methods=['GET', 'POST'])
@user_required
def addreview(itemid):
    item = get_item(itemid)
    if not item:
        return redirect(url_for('index'))
    if request.method == 'POST':
        f = request.form
        try:
            rating = int(f['rate'])
            assert 1 <= rating <= 5
        except (ValueError, AssertionError, KeyError):
            flash('Pick a rating from 1 to 5')
            return redirect(url_for('addreview', itemid=itemid))
        q('insert into reviews(username,itemid,title,review,rating) values(%s,uuid_to_bin(%s),%s,%s,%s) '
          'on duplicate key update title=values(title),review=values(review),rating=values(rating),date=now()',
          [session['user'], itemid, f['title'].strip(), f['review'].strip(), rating], commit=True)
        flash('Thanks for your review')
        return redirect(url_for('description', itemid=itemid))
    return render_template('review.html', item=item)


if __name__ == '__main__':
    app.run(debug=True)
