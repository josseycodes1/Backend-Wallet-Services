# Wallet Service

A Django-based wallet service with Paystack integration, JWT authentication, and API key management.

## Features

- Google OAuth for user authentication
- Wallet creation and management
- Paystack integration for deposits
- Wallet-to-wallet transfers
- API key system for service-to-service access
- Transaction history and statistics
- Comprehensive logging with structlog
- Swagger/OpenAPI documentation

## Prerequisites

- Python 3.8+
- PostgreSQL (or SQLite for development)
- Redis (optional, for caching)
- Paystack account for payment processing

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd wallet_service