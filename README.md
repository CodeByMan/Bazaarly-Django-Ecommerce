<div align="center">

# 🛍️ Bazaarly — Django E-Commerce Storefront

A secure Django MVT e-commerce prototype for browsing a Pakistan-focused catalog, managing guest or signed-in carts, collecting checkout addresses, and simulating Stripe test-mode payments.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab?style=for-the-badge&logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.2-092e20?style=for-the-badge&logo=django&logoColor=white)
![Database](https://img.shields.io/badge/Database-SQLite%20%7C%20PostgreSQL-4169e1?style=for-the-badge&logo=postgresql&logoColor=white)
![Payments](https://img.shields.io/badge/Payments-Stripe%20Test%20Mode-635bff?style=for-the-badge&logo=stripe&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-17%20Automated-22c55e?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-f97316?style=for-the-badge)

</div>

---

## 📌 Project Overview

**Bazaarly** is a deliberately scoped, server-rendered Django e-commerce storefront. It demonstrates how a junior Python developer can model a catalog, manage cart state, protect user-scoped orders, validate Pakistan addresses, apply coupons, and integrate a provider-backed payment flow safely in test mode.

The application uses Django’s monolithic **Model–View–Template (MVT)** architecture. Guests can browse products and add items to a session cart; authentication is required only when proceeding to checkout. Signed-in carts, orders, addresses, coupons, payments, and refund requests are isolated to the authenticated user.

This is an educational portfolio prototype. It does not claim live payment processing, inventory reservation, shipping fulfillment, tax calculation, or production webhook reconciliation.

---

## ✨ Features

### 🛒 Storefront and Cart

- 🛍️ Responsive Bazaarly product catalog with search and pagination
- 👀 Product detail pages with category-based fallback visuals
- ➕ Guest and authenticated add-to-cart workflows
- 🔢 Dynamic navbar cart quantity badge
- 🧾 Cart summary with quantity controls and item removal
- 🔐 Authentication required only before checkout
- 🛡️ CSRF-protected POST cart mutations

### 💳 Checkout and Orders

- 📍 Pakistan address forms using PKR-oriented demo data
- 📦 Shipping and billing address capture with default-address options
- 🎟️ Coupon validation with date and usage-window checks
- 💰 Decimal-based monetary calculations instead of floating point
- 💳 Stripe test-mode PaymentIntent flow with persisted idempotency keys
- ⚛️ Atomic local order/payment finalization and rollback handling
- 🔁 Reconciliation-required state for provider/database mismatch scenarios
- 🧾 User-scoped completed orders and refund requests

### 🛡️ Security and Reliability

- 🔒 Explicit development and fail-closed production settings
- 🚫 No real credentials or runtime database included in the repository
- 🧱 Cross-user order, payment, coupon, and refund authorization checks
- 🌐 Safe same-site validation for cart return redirects
- 🧑‍💼 CSRF-protected POST logout
- ✅ Admin refund action restricted to eligible requested refunds
- 📋 Structured Django messages and accessible form feedback
- 🧪 Network-free automated tests with mocked Stripe requests

### 🎨 Portfolio Interface

- 🧡 Premium orange/navy Bazaarly theme
- 📱 Responsive desktop, laptop, tablet, and mobile layouts
- 🔎 Centered navigation search bar and responsive action controls
- 🧩 Reusable templates for navbar, footer, authentication, cart, checkout, and product detail pages
- 👨‍💻 Developer attribution: Muhammad Ali Nawaz 2026

---

## 🖼️ Screenshots

```markdown
| Bazaarly storefront | Product detail | Checkout |
| --- | --- | --- |
| ![Storefront](docs/screenshots/storefront.png) | ![Product detail](docs/screenshots/product-detail.png) | ![Checkout](docs/screenshots/checkout.png) |
```

Screenshots are optional documentation assets and are not required to run the application.

---

## 🧰 Tech Stack

### Backend

- Python 3.10+
- Django 5.2
- Django Allauth
- Crispy Forms with Bootstrap 4 integration
- Stripe Python SDK
- SQLite for local development
- PostgreSQL-compatible production settings

### Frontend

- Django Templates
- HTML5 and semantic form markup
- Responsive custom CSS
- Inline SVG interface icons
- Local static assets under `static_in_env/`

### Quality Assurance

- Django system checks
- Pytest and Django test integration
- Mocked Stripe provider requests
- CSRF, authorization, cart-state, coupon, and payment tests
- Python syntax compilation

---

## 📁 Folder Structure

```text
bazaarly-django-ecommerce/
├── core/
│   ├── admin.py
│   ├── forms.py
│   ├── models.py
│   ├── urls.py
│   ├── views.py
│   ├── context_processors.py
│   ├── fixtures/karachi_demo.json
│   └── migrations/
├── djecommerce/
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── static_in_env/
│   ├── css/
│   ├── img/
│   └── js/
├── templates/
│   ├── account/
│   ├── base.html
│   ├── navbar.html
│   ├── home.html
│   ├── product.html
│   ├── order_summary.html
│   └── checkout.html
├── .env.example
├── .gitignore
├── LICENSE
├── manage.py
├── pytest.ini
├── requirements.txt
├── SECURITY.md
└── README.md
```

Runtime databases, uploaded media, collected static output, secrets, virtual environments, caches, and bytecode are excluded from Git.

---

## 🔐 Environment Variables

Never commit `.env` or real credentials. Copy `.env.example` locally and add only Stripe **test-mode** values when manually exercising payments.

```env
SECRET_KEY=replace-with-a-long-random-development-key
STRIPE_TEST_PUBLIC_KEY=pk_test_replace_me
STRIPE_TEST_SECRET_KEY=sk_test_replace_me
```

Local development uses SQLite and Django’s console email backend. Stripe credentials are optional for catalog, cart, address, and test-suite workflows.

---

## 🚀 Getting Started on Windows

### Prerequisites

Install Python 3.10 or newer. Python 3.13 is supported. Windows PowerShell and Command Prompt are both supported.

### 1. Create the Virtual Environment

```bat
cd /d "D:\Resumes\Projects\Python\Projects\Bazaarly"
py -m venv ecom_website_env
call ecom_website_env\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
copy .env.example .env
set DJANGO_SETTINGS_MODULE=djecommerce.settings.development
```

### 2. Initialize the Database and Demo Catalog

```bat
python manage.py check
python manage.py migrate
python manage.py loaddata core\fixtures\karachi_demo.json
```

### 3. Run the Complete Project

```bat
python manage.py runserver 127.0.0.1:8000
```

Open `http://127.0.0.1:8000/` in a browser. Add products as a guest, open the cart, and sign in only when proceeding to checkout.

### 4. Run Tests

```bat
python manage.py makemigrations --check --dry-run
python -m pytest -q
```

The suite covers authentication, authorization, cart and CSRF safety, catalog search, coupons, decimal totals, mocked Stripe outcomes, rollback behavior, fixture loading, and settings safety. Tests do not make network requests.

---

## 🐧 Linux/macOS Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
export DJANGO_SETTINGS_MODULE=djecommerce.settings.development
python manage.py migrate
python manage.py loaddata core/fixtures/karachi_demo.json
python -m pytest -q
python manage.py runserver 127.0.0.1:8000
```

---

## 💳 Stripe Test-Mode Checkout

Add fresh Stripe test keys to the local `.env` only:

```env
STRIPE_TEST_PUBLIC_KEY=pk_test_your_key
STRIPE_TEST_SECRET_KEY=sk_test_your_key
```

Never enter a real card. Automated tests mock provider requests. The application uses PaymentIntents and idempotency keys, but a real deployment would still require signed Stripe webhooks and an operational reconciliation worker.

---

## ⚠️ Known Limitations

- Stripe integration is test mode only.
- No live-payment, shipping-provider, tax-engine, or inventory-reservation claim.
- Refund requests are recorded for staff review; admin approval does not transfer money.
- Database and uploaded media are local by default.
- Bundled Bootstrap/MDB compatibility assets are intentionally lightweight for this portfolio prototype.

---

## 📄 License and Attribution

Project code is available under the MIT License. Third-party assets retain their own notices and licenses.

**Developer by Muhammad Ali Nawaz — 2026**

Safe resume claim:

> Built a secure Django e-commerce prototype with guest and authenticated carts, Pakistan/PKR checkout, coupons, user-scoped orders, CSRF protection, and Stripe test-mode PaymentIntents.
