# VIKMO DealerDesk — AI/ML Intern Assignment

DealerDesk is a Django and PostgreSQL backend for a dealer-management workflow. It supports product catalogue and inventory operations, dealer records, draft orders, order status transitions, supplier synchronization, and forecasting-related endpoints.

## Features

- **Product catalogue:** Paginated product listing and product lookup.
- **Dealer management:** Dealer listing and dealer creation.
- **Inventory:** Inventory updates through the API.
- **Order management:** Draft-order creation, validation, and order confirmation/cancellation workflows.
- **Supplier synchronization:** Supplier data synchronization endpoint with response summaries.
- **Dealer Assistant:** Chat endpoint with dealer-context validation.
- **Forecasting and reorder suggestions:** Forecast data and API endpoints for forecasting and inventory replenishment recommendations.
- **Health check:** API endpoint for checking service availability.
- **Configuration:** Database and integration settings are supplied through environment variables.

## Technology Stack

- Python
- Django
- Django REST Framework
- PostgreSQL
- Requests for HTTP integrations

## Prerequisites

- Python 3.11 or later, compatible with the project's dependencies
- PostgreSQL database
- Git
- Windows PowerShell, macOS Terminal, or Linux shell

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/Manasa8746/VIKMO-DealerDesk.git
cd VIKMO-DealerDesk
```

### 2. Create and activate a virtual environment

**Windows PowerShell:**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**macOS/Linux:**

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

Create a local `.env` file based on `.env.example` and configure the PostgreSQL connection and any required integration settings.

Keep `.env` private. Never commit database credentials, API keys, or other secrets to GitHub.

### 5. Apply database migrations

```bash
python manage.py migrate
```

### 6. Seed the database

```bash
python manage.py seed_data
```

The seed command loads the catalogue and dealer data supplied with the project. Run it in the intended test environment and verify the resulting database counts before testing.

### 7. Start the development server

```bash
python manage.py runserver
```

The default local address is:

`http://127.0.0.1:8000/`

## Verification

Run Django's configuration and model checks:

```bash
python manage.py check
```

Run the bundled smoke tests against the local server:

```bash
python smoke_test.py --all
```

Start the Django server in a separate terminal before running the smoke tests. The tests exercise basic API contracts, response formats, and selected workflows; they do not guarantee that every edge case or production scenario is covered.

## Supplier Integration

The supplier synchronization endpoint depends on the configured supplier service. If using the bundled mock supplier, follow the mock service's setup instructions and configure `SUPPLIER_API_URL` and any required credentials in the local environment.

## Forecasting

The project includes forecast data at `ml/forecast.csv` and API endpoints for forecast retrieval and reorder suggestions. Forecast outputs should be treated as decision-support information and evaluated against actual sales and inventory history before being used for purchasing decisions.

## Security Notes

- Keep `.env` and local credentials out of version control.
- Use placeholder values in `.env.example`.
- Configure appropriate authentication and permissions before deploying the service publicly.
- Do not use production credentials or production data for local testing.

## Known Limitations and Future Improvements

- Expand automated tests to cover validation failures, edge cases, and concurrent inventory updates.
- Evaluate forecast quality using suitable metrics and held-out historical data.
- Strengthen authentication, permissions, logging, and monitoring for production deployment.
- Validate supplier integration against the intended external service.

## Repository

GitHub: https://github.com/Manasa8746/VIKMO-DealerDesk