# Implementation Decisions — VIKMO DealerDesk

## 1. Backend Architecture
Django is used for the backend because it provides a structured framework for implementing business logic, request handling, validation, and database integration.

## 2. Database
PostgreSQL is used for persistent application data. Database connection settings are supplied through environment variables rather than hard-coded credentials.

## 3. Configuration and Secrets
Environment-specific values are stored in a local `.env` file. The `.env` file is excluded from Git, and `.env.example` provides placeholder configuration for setup.

## 4. API Design
The API follows consistent endpoint conventions and uses validation to handle invalid input. Monetary values should be represented with two decimal places, and list endpoints should support pagination where applicable.

## 5. Inventory and Orders
Order processing should validate requested products and quantities against the current catalogue and available inventory. Prices should be derived from the current catalogue rather than trusted from client input.

## 6. Forecasting and Reordering
Forecasting and reorder recommendations should use available sales-history and inventory data. Recommendations are decision-support outputs and should be reviewed against actual business conditions before purchasing.

## 7. External Integrations
External supplier services and AI providers should be configured through environment variables. Integration failures should be handled safely without exposing credentials.

## 8. Limitations and Future Improvements
- Add or strengthen automated tests for API validation and edge cases.
- Evaluate forecasting accuracy using appropriate validation metrics.
- Add production-grade authentication and permissions where required.
- Integrate and test against the actual supplier service before production use.
- Improve logging, monitoring, and deployment configuration.

## 9. Security
Secrets, database credentials, and API keys must not be committed to the public repository. Only placeholder values belong in example configuration files.
