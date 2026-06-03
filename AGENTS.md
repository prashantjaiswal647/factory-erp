# Munshi AI - Master Project Context

## Project Overview

Munshi AI is an AI-Powered Smart ERP / Factory Supervisor SaaS designed for paper cup and paper glass manufacturing units.

The goal is to digitize and automate factory operations, reduce manual bookkeeping, provide real-time business visibility, and gradually evolve into an AI Supervisor capable of monitoring production, inventory, finance, CRM, and factory operations.

---

# Current Production Environment

## Live URLs

Dashboard:
https://munshiai.co.in

API:
https://munshiai.co.in/api

n8n:
https://n8n.munshiai.co.in

---

# Technology Stack

Backend:

* FastAPI
* Python

Frontend:

* React
* Vite

Database:

* PostgreSQL

Infrastructure:

* Docker Compose

Reverse Proxy:

* Caddy

Automation:

* n8n

Hosting:

* Hostinger VPS

---

# Multi-Tenant Architecture

The entire system is multi-tenant.

Core rule:

Every business record must belong to a specific factory.

Factory isolation is mandatory.

Never allow data leakage between factories.

Important field:

factory_id

Every query, API, report, dashboard, inventory calculation, attendance record, order, invoice, production record and financial transaction must remain isolated using factory_id.

This rule must never be broken.

---

# Authentication System

Current status:

Implemented:

* Login
* Signup
* Session-based authentication

Planned:

* Google Login
* Country Code based phone number signup
* Mobile number login
* Subscription-aware access control

Requirements:

* Existing authentication should never break.
* Backend and frontend changes must remain synchronized.

Security rules:

* Internal n8n/API automation endpoints must require `X-N8N-API-KEY`.
* `N8N_API_KEY`, `JWT_SECRET_KEY`, and Super Admin secrets must fail closed when missing. Do not add hardcoded fallback secrets.
* Machine template manual approval is a Super Admin-only action. Factory Owner/Sub-Owner users may submit templates but must not approve them manually.

---

# Factory Onboarding Module

Purpose:

Capture factory setup information and initialize the ERP.

Factory onboarding should collect:

* Factory details
* Product types
* Machine information
* Worker information
* Initial inventory
* Existing attendance records
* Existing financial records

Special Requirement:

Historical attendance entered during onboarding must merge with future attendance records.

Salary calculations must include:

Past Attendance
+
Future Daily Attendance
=======================

Final Salary Calculation

---

# Inventory Module

Purpose:

Track all inventory movement.

Current inventory categories:

Raw Material:

* Paper Blank
* Bottom

Consumables:

* Mobil Oil
* Paraffin Oil
* Electricity Usage

Packaging:

* Plastic Packets
* Boxes

Finished Goods:

* Paper Cups
* Paper Glasses

Requirements:

Inventory must support:

* Stock In
* Stock Out
* Current Stock
* Inventory History
* Inventory Valuation

UI Requirement:

Avoid horizontal scrolling.

Display inventory category-wise.

Example:

Section 1:
Bottom Inventory

Section 2:
Blank Inventory

Section 3:
Packaging Inventory

Section 4:
Finished Goods Inventory

---

# Production Module

Purpose:

Track daily manufacturing.

Production data includes:

* Machine
* Product
* Shift
* Production Quantity
* Wastage
* Operator

Business Logic:

Production affects:

Raw Material Stock
↓
Wastage
↓
Finished Goods Stock

All calculations must remain traceable.

---

# Wastage Module

Purpose:

Track production losses.

Examples:

* Blank wastage
* Bottom wastage
* Packaging wastage

Requirements:

Separate wastage reporting.

Historical wastage analysis.

Machine-wise wastage tracking.

---

# Worker Management Module

Purpose:

Manage factory workforce.

Features:

* Worker profiles
* Attendance
* Salary calculation

Requirement:

Attendance added during onboarding must merge with attendance recorded later.

---

# Finance Module

Purpose:

Track money movement.

Features:

* Purchases
* Expenses
* Sales
* Payments Received
* Outstanding Payments

Future:

* Profit & Loss
* Cash Flow
* AI Insights

---

# CRM Module

Purpose:

Manage customers.

Features:

* Customer database
* Orders
* Outstanding balances
* Payment tracking

Future:

* Customer analytics
* Purchase trends

---

# Order Management Module

Purpose:

Track customer orders.

Flow:

Order Created
↓
Inventory Reserved
↓
Dispatch
↓
Invoice
↓
Payment Collection

---

# Dispatch Module

Purpose:

Track shipment of finished goods.

Requirements:

* Dispatch records
* Customer linkage
* Inventory deduction

---

# Invoice Module

Purpose:

Generate customer invoices.

Requirements:

* Customer linked invoices
* Payment status
* Outstanding tracking

---

# Payment Reminder Automation

Platform:
n8n

Purpose:

Automatically remind customers about pending payments.

Future Flow:

Customer Due
↓
n8n Workflow
↓
Reminder Message
↓
Follow-up Tracking

---

# AI Supervisor Vision

Long-Term Goal

Gemma (Groq) powered AI Supervisor.

Responsibilities:

* Production Monitoring
* Inventory Monitoring
* Costing Analysis
* Purchase Suggestions
* Wastage Detection
* Financial Insights
* Outstanding Payment Tracking
* Factory Health Monitoring

AI should act like a digital factory manager.

---

# Dashboard Requirements

Dashboard must prioritize readability.

Avoid excessive charts.

Prefer:

* Key Metrics
* Current Stock
* Production Summary
* Outstanding Payments
* Customer Dues
* Alerts

Factory owners should understand business status within 30 seconds.

---

# Development Rules

Before changing code:

1. Inspect existing implementation.
2. Understand backend and frontend flow.
3. Preserve factory_id isolation.
4. Preserve database compatibility.
5. Avoid unnecessary refactoring.

After changes:

1. Show changed files.
2. Explain root cause.
3. Provide local test steps.
4. Provide deployment commands.

---

# Deployment Workflow

Local Development
↓
Testing
↓
Git Commit
↓
Git Push
↓
Hostinger Pull
↓
Docker Rebuild
↓
Production Verification

Commands:

git add .
git commit
git push origin main

VPS:

cd ~/factory-erp

git pull origin main

docker-compose up -d --force-recreate --build web api caddy

---

# Current Development Goal

Transform Munshi AI from a working ERP into a production-ready SaaS that can be sold to manufacturing units.

Priorities:

1. Stability
2. Data Accuracy
3. Factory Isolation
4. User Experience
5. Automation
6. Subscription Management
7. AI Supervisor
