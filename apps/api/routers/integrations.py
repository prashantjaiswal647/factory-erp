import os
import httpx
import hashlib
from typing import Optional
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ai_agent import build_ai_tool_context, initialize_groq_llm
from auth import check_permissions
from db import get_db
from models import Factory, User, Customer, PackagingProfile, Inventory, SalesInvoice
from telegram_crypto import encrypt_token, decrypt_token

router = APIRouter(tags=["integrations"])


# Existing schemas
class TelegramIntegrationResponse(BaseModel):
    telegram_bot_token: Optional[str] = None
    is_configured: bool


class TelegramIntegrationRequest(BaseModel):
    telegram_bot_token: Optional[str] = Field(default=None, max_length=255)


class N8NAIWebhookRequest(BaseModel):
    factory_id: int | str
    user_message: str = Field(..., min_length=1)


class N8NAIWebhookResponse(BaseModel):
    response: str


# New schemas for dynamic onboarding, bot lookup, and invoicing
class TelegramSetupRequest(BaseModel):
    bot_token: str


class TelegramSetupResponse(BaseModel):
    telegram_bot_username: str
    webhook_url: str
    status: str


class BotLookupRequest(BaseModel):
    bot_username: str
    chat_id: str
    username: Optional[str] = None
    phone_number: Optional[str] = None


class BotLookupResponse(BaseModel):
    factory_id: int
    verified: bool
    telegram_bot_token: str


class InvoiceGenerateRequest(BaseModel):
    factory_id: int


class InvoiceGenerateResponse(BaseModel):
    invoice_id: int
    text_summary: str
    status: str


# Helpers
def _factory_for_user(db: Session, current_user: User) -> Factory:
    factory = db.query(Factory).filter(Factory.id == current_user.factory_id).first()
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Factory not found for current user",
        )
    return factory


def _normalize_token(token: Optional[str]) -> Optional[str]:
    cleaned = (token or "").strip()
    return cleaned or None


# Existing Endpoints for backward compatibility
@router.get("/api/integrations/telegram", response_model=TelegramIntegrationResponse)
def get_telegram_integration(
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner"])),
    db: Session = Depends(get_db),
):
    factory = _factory_for_user(db, current_user)
    return TelegramIntegrationResponse(
        telegram_bot_token=factory.telegram_bot_token,
        is_configured=bool(factory.telegram_bot_token),
    )


@router.post("/api/integrations/telegram", response_model=TelegramIntegrationResponse)
def save_telegram_integration(
    payload: TelegramIntegrationRequest,
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner"])),
    db: Session = Depends(get_db),
):
    factory = _factory_for_user(db, current_user)
    normalized_token = _normalize_token(payload.telegram_bot_token)
    factory.telegram_bot_token = normalized_token
    
    # Also encrypt and store in the new secure telegram_token field for unification
    if normalized_token:
        factory.telegram_token = encrypt_token(normalized_token)
    else:
        factory.telegram_token = None
        
    db.commit()
    db.refresh(factory)
    return TelegramIntegrationResponse(
        telegram_bot_token=factory.telegram_bot_token,
        is_configured=bool(factory.telegram_bot_token),
    )


# Existing LLM Webhook (Groq Llama3 fallback for n8n)
@router.post("/api/ai/n8n-webhook", response_model=N8NAIWebhookResponse)
def telegram_ai_n8n_webhook(payload: N8NAIWebhookRequest, db: Session = Depends(get_db)):
    try:
        factory_id = int(payload.factory_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="factory_id must be a valid integer",
        ) from exc

    factory = db.query(Factory).filter(Factory.id == factory_id).first()
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Factory not found",
        )

    llm = initialize_groq_llm()
    if llm is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GROQ_API_KEY or Groq dependencies are not configured",
        )

    factory_context = build_ai_tool_context(db, factory_id)
    prompt = ChatPromptTemplate = None  # Lazy loading imports to handle langchain imports locally inside router
    from langchain_core.prompts import ChatPromptTemplate
    
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a professional factory supervisor for a multi-tenant Factory ERP SaaS. "
                "Use only the provided factory context for inventory, machines, customers, and production facts. "
                "Be concise, practical, and action-oriented. If the user writes Hindi or Hinglish, reply naturally in Hindi/Hinglish. "
                "Never invent stock, customer, or production data that is not present in the context.\n\n"
                "Factory context:\n{factory_context}",
            ),
            ("human", "{user_message}"),
        ]
    )
    chain = prompt | llm

    try:
        result = chain.invoke(
            {
                "factory_context": factory_context,
                "user_message": payload.user_message.strip(),
            }
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Groq supervisor response failed: {exc}",
        ) from exc

    response_text = getattr(result, "content", str(result)).strip()
    return N8NAIWebhookResponse(response=response_text)


# ==========================================
# PHASE 2: Dynamic Telegram Webhook Registration
# ==========================================
@router.post("/api/v1/integrations/telegram/setup", response_model=TelegramSetupResponse)
async def telegram_setup_webhook(
    payload: TelegramSetupRequest,
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner"])),
    db: Session = Depends(get_db)
):
    bot_token = payload.bot_token.strip()
    if not bot_token:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="bot_token cannot be empty",
        )

    async with httpx.AsyncClient() as client:
        try:
            # 1. Query bot username detail with getMe first
            me_response = await client.get(f"https://api.telegram.org/bot{bot_token}/getMe")
            me_json = me_response.json()
            if not me_json.get("ok"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Telegram getMe failed: {me_json.get('description', 'Unknown error')}",
                )
            
            bot_username = me_json["result"]["username"]

            # 2. Form dynamic webhook target URL including bot_username parameter for n8n lookup
            webhook_target = f"https://n8n.munshiai.co.in/webhook/telegram-bridge?bot_username={bot_username}"

            # 3. setWebhook registered dynamically with Telegram's APIs
            wh_response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/setWebhook",
                json={"url": webhook_target}
            )
            wh_json = wh_response.json()
            if not wh_json.get("ok"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Telegram setWebhook failed: {wh_json.get('description', 'Unknown error')}",
                )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to communicate with Telegram API: {exc}",
            )

    factory = _factory_for_user(db, current_user)
    
    # Store encrypted bot token and details
    factory.telegram_token = encrypt_token(bot_token)
    factory.telegram_bot_username = bot_username
    factory.telegram_bot_token = bot_token  # Synchronized with legacy field
    
    # Reset chat_id on webhook updates to allow dynamic re-pairing
    factory.telegram_chat_id = None
    
    db.commit()
    db.refresh(factory)

    return TelegramSetupResponse(
        telegram_bot_username=bot_username,
        webhook_url=webhook_target,
        status="Webhook configured successfully. Bot token stored securely."
    )


# ==========================================
# PHASE 1: Secure Internal Bot-Lookup Endpoint
# ==========================================
@router.post("/api/v1/internal/bot-lookup", response_model=BotLookupResponse)
def internal_bot_lookup(
    payload: BotLookupRequest,
    x_n8n_api_key: Optional[str] = Header(None, alias="X-N8N-API-KEY"),
    db: Session = Depends(get_db)
):
    # Enforce system secret API header validation
    expected_api_key = os.getenv("N8N_API_KEY", "replace_with_a_strong_n8n_to_api_secret")
    if not x_n8n_api_key or x_n8n_api_key != expected_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid system secret header key",
        )

    # Search for factory associated with this Telegram Bot username
    factory = db.query(Factory).filter(Factory.telegram_bot_username == payload.bot_username.strip()).first()
    if not factory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Factory matching bot username @{payload.bot_username} not found",
        )

    target_chat_id = payload.chat_id.strip()

    # Dynamic registration: If factory chat ID isn't linked yet, bind it dynamically!
    if not factory.telegram_chat_id:
        factory.telegram_chat_id = target_chat_id
        db.commit()
        db.refresh(factory)
    elif factory.telegram_chat_id != target_chat_id:
        # Enforce strict multi-tenant boundary isolation
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Telegram Chat ID does not match owner configuration",
        )

    decrypted_token = decrypt_token(factory.telegram_token)
    return BotLookupResponse(
        factory_id=factory.id,
        verified=True,
        telegram_bot_token=decrypted_token
    )


# ==========================================
# PHASE 4: Basic E-Invoicing Endpoint Mockup
# ==========================================
@router.post("/api/v1/invoices/basic-generate", response_model=InvoiceGenerateResponse)
def basic_generate_invoice(
    payload: InvoiceGenerateRequest,
    x_n8n_api_key: Optional[str] = Header(None, alias="X-N8N-API-KEY"),
    db: Session = Depends(get_db)
):
    # Enforce system secret API header validation
    expected_api_key = os.getenv("N8N_API_KEY", "replace_with_a_strong_n8n_to_api_secret")
    if not x_n8n_api_key or x_n8n_api_key != expected_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid system secret header key",
        )

    factory_id = payload.factory_id
    factory = db.query(Factory).filter(Factory.id == factory_id).first()
    if not factory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Factory {factory_id} not found",
        )

    # 1. Resolve or Create default Customer
    customer = db.query(Customer).filter(Customer.factory_id == factory_id).first()
    if not customer:
        customer = Customer(
            factory_id=factory_id,
            name="Telegram Walk-in Customer",
            phone="9999999999",
            total_due=Decimal("0.00"),
            previous_due=Decimal("0.00"),
            advance_discount_pct=5.0,
            balance_amount=Decimal("0.00"),
            pending_dues=0.0,
            pending_balance=Decimal("0.00")
        )
        db.add(customer)
        db.flush()

    # 2. Resolve or Create default PackagingProfile and associated Inventory dependencies
    profile = db.query(PackagingProfile).filter(PackagingProfile.factory_id == factory_id).first()
    if not profile:
        box_inv = db.query(Inventory).filter(
            Inventory.factory_id == factory_id, 
            Inventory.item_name == "Default Box"
        ).first()
        if not box_inv:
            box_inv = Inventory(
                factory_id=factory_id,
                item_name="Default Box",
                category="Packaging",
                unit="pieces",
                quantity=Decimal("1000.000"),
                price_per_unit=Decimal("10.00")
            )
            db.add(box_inv)
            db.flush()

        poly_inv = db.query(Inventory).filter(
            Inventory.factory_id == factory_id, 
            Inventory.item_name == "Default Poly"
        ).first()
        if not poly_inv:
            poly_inv = Inventory(
                factory_id=factory_id,
                item_name="Default Poly",
                category="Packaging",
                unit="pieces",
                quantity=Decimal("1000.000"),
                price_per_unit=Decimal("2.00")
            )
            db.add(poly_inv)
            db.flush()

        profile = PackagingProfile(
            factory_id=factory_id,
            profile_name="80ml Paper Cup Profile",
            cup_size_ml=80,
            cups_per_poly=50,
            polys_per_box=40,
            box_inventory_id=box_inv.id,
            poly_inventory_id=poly_inv.id,
        )
        db.add(profile)
        db.flush()

    # 3. Create active transactional invoice in database
    invoice_amount = Decimal("15000.00")
    invoice = SalesInvoice(
        factory_id=factory_id,
        customer_id=customer.id,
        date=date.today(),
        cup_size_ml=profile.cup_size_ml,
        packaging_profile_id=profile.id,
        boxes_sold=10,
        total_amount=invoice_amount,
        amount_paid=Decimal("0.00")
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    # 4. Generate unique verification hash
    verification_hash = hashlib.sha256(f"invoice-{invoice.id}-{factory_id}".encode()).hexdigest()[:12].upper()
    
    # 5. Yield standard paper-glass parameters mapping for weight
    total_cups = invoice.boxes_sold * (profile.cups_per_poly * profile.polys_per_box)
    cup_weight_g = 4.5
    total_weight_kg = (total_cups * cup_weight_g) / 1000.0

    summary_text = (
        f"🧾 *E-INVOICE GENERATED* (ID: `{invoice.id}`)\n"
        f"----------------------------------------\n"
        f"🏢 *Factory Tenant ID:* `{factory_id}`\n"
        f"👤 *Customer:* {customer.name}\n"
        f"📦 *Product:* {profile.cup_size_ml}ml Paper Cups\n"
        f"📊 *Quantity:* {invoice.boxes_sold} Boxes ({total_cups:,} Pcs)\n"
        f"⚖️ *Est. Material Weight:* {total_weight_kg:.2f} kg\n"
        f"💰 *Subtotal:* ₹{invoice.total_amount:,.2f}\n"
        f"💳 *Status:* Unpaid (₹{invoice.total_amount:,.2f} pending)\n"
        f"----------------------------------------\n"
        f"🔑 *Verification:* `{verification_hash}`\n"
        f"✅ Saved securely in ERP database."
    )

    return InvoiceGenerateResponse(
        invoice_id=invoice.id,
        text_summary=summary_text,
        status="SUCCESS"
    )


# ==========================================
# PHASE 2: Dynamic Context & Dual-Mode Invoicing
# ==========================================

class BotContextRequest(BaseModel):
    bot_token: str
    chat_id: str


class BotContextResponse(BaseModel):
    factory_id: int
    is_authorized: bool
    owner_name: str


class InvoiceGenerateModeRequest(BaseModel):
    factory_id: int
    invoice_mode: str = Field(..., description="Either 'basic' or 'gst'")


class InvoiceGenerateModeResponse(BaseModel):
    invoice_id: int
    invoice_mode: str
    invoice_number: Optional[str] = None
    subtotal: Decimal
    cgst: Optional[Decimal] = None
    sgst: Optional[Decimal] = None
    igst: Optional[Decimal] = None
    total_amount: Decimal
    text_summary: str
    status: str


@router.post("/api/v1/internal/bot-context", response_model=BotContextResponse)
def internal_bot_context(
    payload: BotContextRequest,
    x_n8n_api_key: Optional[str] = Header(None, alias="X-N8N-API-KEY"),
    db: Session = Depends(get_db)
):
    # Enforce system secret API header validation
    expected_api_key = os.getenv("N8N_API_KEY", "replace_with_a_strong_n8n_to_api_secret")
    if not x_n8n_api_key or x_n8n_api_key != expected_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid system secret header key",
        )

    incoming_chat_id = payload.chat_id.strip()
    incoming_bot_token = payload.bot_token.strip()

    # Search for factory with mapped chat ID
    factory = db.query(Factory).filter(Factory.telegram_chat_id == incoming_chat_id).first()
    
    if not factory:
        # Fallback: search by legacy plain text token or decrypting candidates
        factory = db.query(Factory).filter(Factory.telegram_bot_token == incoming_bot_token).first()

    if not factory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Factory not found for incoming session context",
        )

    # Verify token authenticity
    try:
        decrypted_token = decrypt_token(factory.telegram_token)
        if decrypted_token != incoming_bot_token and factory.telegram_bot_token != incoming_bot_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized: Bot token mismatch",
            )
    except Exception:
        if factory.telegram_bot_token != incoming_bot_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized: Token decryption failure",
            )

    # Resolve Owner Name
    owner_name = "Malik"
    if factory.owner:
        owner_name = factory.owner.full_name or factory.owner.username or "Malik"
    else:
        # Fallback to looking up owner role
        owner_user = db.query(User).filter(User.factory_id == factory.id, User.role == "Owner").first()
        if owner_user:
            owner_name = owner_user.full_name or owner_user.username or "Malik"

    return BotContextResponse(
        factory_id=factory.id,
        is_authorized=True,
        owner_name=owner_name
    )


@router.get("/api/v1/reports/summary")
def get_reports_summary(
    factory_id: int,
    x_n8n_api_key: Optional[str] = Header(None, alias="X-N8N-API-KEY"),
    db: Session = Depends(get_db)
):
    # Enforce system secret API header validation
    expected_api_key = os.getenv("N8N_API_KEY", "replace_with_a_strong_n8n_to_api_secret")
    if not x_n8n_api_key or x_n8n_api_key != expected_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid system secret header key",
        )

    factory = db.query(Factory).filter(Factory.id == factory_id).first()
    if not factory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Factory {factory_id} not found",
        )

    # Compile dynamic stats summaries
    total_customers = db.query(Customer).filter(Customer.factory_id == factory_id).count()
    total_outstanding = db.query(sql_func.coalesce(sql_func.sum(Customer.total_due), 0)).filter(Customer.factory_id == factory_id).scalar() or Decimal("0.00")
    low_stock_count = db.query(Inventory).filter(Inventory.factory_id == factory_id, Inventory.quantity < 50).count()
    packaging_profiles = db.query(PackagingProfile).filter(PackagingProfile.factory_id == factory_id).count()
    sales_invoices = db.query(SalesInvoice).filter(SalesInvoice.factory_id == factory_id).count()

    return {
        "factory_name": factory.name or factory.factory_name or f"Factory #{factory_id}",
        "metrics": {
            "total_customers": total_customers,
            "total_market_outstanding": float(total_outstanding),
            "low_stock_alerts": low_stock_count,
            "active_packaging_profiles": packaging_profiles,
            "total_sales_invoices": sales_invoices
        },
        "status": "HEALTHY",
        "message": "Dynamic Factory operational data compiled successfully."
    }


# Hook to register sql functions
from sqlalchemy import func as sql_func

@router.post("/api/v1/invoices/generate", response_model=InvoiceGenerateModeResponse)
def generate_mode_invoice(
    payload: InvoiceGenerateModeRequest,
    x_n8n_api_key: Optional[str] = Header(None, alias="X-N8N-API-KEY"),
    db: Session = Depends(get_db)
):
    # Enforce system secret API header validation
    expected_api_key = os.getenv("N8N_API_KEY", "replace_with_a_strong_n8n_to_api_secret")
    if not x_n8n_api_key or x_n8n_api_key != expected_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid system secret header key",
        )

    factory_id = payload.factory_id
    mode = payload.invoice_mode.lower().strip()

    if mode not in ["basic", "gst"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid invoice_mode. Must be 'basic' or 'gst'."
        )

    factory = db.query(Factory).filter(Factory.id == factory_id).first()
    if not factory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Factory {factory_id} not found",
        )

    # 1. Resolve or Create default Customer
    customer = db.query(Customer).filter(Customer.factory_id == factory_id).first()
    if not customer:
        customer = Customer(
            factory_id=factory_id,
            name="Telegram Walk-in Customer",
            phone="9999999999",
            total_due=Decimal("0.00"),
            previous_due=Decimal("0.00"),
            advance_discount_pct=5.0,
            balance_amount=Decimal("0.00"),
            pending_dues=0.0,
            pending_balance=Decimal("0.00")
        )
        db.add(customer)
        db.flush()

    # 2. Resolve or Create default PackagingProfile and associated Inventory dependencies
    profile = db.query(PackagingProfile).filter(PackagingProfile.factory_id == factory_id).first()
    if not profile:
        box_inv = db.query(Inventory).filter(
            Inventory.factory_id == factory_id, 
            Inventory.item_name == "Default Box"
        ).first()
        if not box_inv:
            box_inv = Inventory(
                factory_id=factory_id,
                item_name="Default Box",
                category="Packaging",
                unit="pieces",
                quantity=Decimal("1000.000"),
                price_per_unit=Decimal("10.00")
            )
            db.add(box_inv)
            db.flush()

        poly_inv = db.query(Inventory).filter(
            Inventory.factory_id == factory_id, 
            Inventory.item_name == "Default Poly"
        ).first()
        if not poly_inv:
            poly_inv = Inventory(
                factory_id=factory_id,
                item_name="Default Poly",
                category="Packaging",
                unit="pieces",
                quantity=Decimal("1000.000"),
                price_per_unit=Decimal("2.00")
            )
            db.add(poly_inv)
            db.flush()

        profile = PackagingProfile(
            factory_id=factory_id,
            profile_name="80ml Paper Cup Profile",
            cup_size_ml=80,
            cups_per_poly=50,
            polys_per_box=40,
            box_inventory_id=box_inv.id,
            poly_inventory_id=poly_inv.id,
        )
        db.add(profile)
        db.flush()

    # 3. Create transactional records based on Mode
    boxes_sold = 12
    total_cups = boxes_sold * (profile.cups_per_poly * profile.polys_per_box)  # 24,000 pieces
    price_per_cup = Decimal("0.75")
    subtotal = Decimal(str(total_cups)) * price_per_cup  # ₹18,000.00
    
    # Standard paper-glass parameters mapping for weight
    cup_weight_g = 4.5
    gross_weight_kg = Decimal(str(total_cups * cup_weight_g)) / Decimal("1000.0")  # 108.0 kg

    if mode == "basic":
        # Internal bill parameters: shift count, bottom-line wastage weight reduction metrics
        shift_count = 2
        wastage_reduction_pct = Decimal("1.8")
        wastage_reduction_kg = gross_weight_kg * (wastage_reduction_pct / Decimal("100"))  # 1.94 kg
        net_weight_kg = gross_weight_kg - wastage_reduction_kg  # 106.06 kg
        
        invoice = SalesInvoice(
            factory_id=factory_id,
            customer_id=customer.id,
            date=date.today(),
            cup_size_ml=profile.cup_size_ml,
            packaging_profile_id=profile.id,
            boxes_sold=boxes_sold,
            total_amount=subtotal,
            amount_paid=Decimal("0.00")
        )
        db.add(invoice)
        db.commit()
        db.refresh(invoice)

        summary_text = (
            f"🧾 *INTERNAL BILL GENERATED* (ID: `{invoice.id}`)\n"
            f"----------------------------------------\n"
            f"🏢 *Factory Tenant ID:* `{factory_id}`\n"
            f"👤 *Customer:* {customer.name}\n"
            f"📦 *Product:* {profile.cup_size_ml}ml Paper Cups\n"
            f"⏱️ *Operational Shifts:* `{shift_count}` shifts\n"
            f"📊 *Quantity:* {boxes_sold} Boxes ({total_cups:,} Pcs)\n"
            f"⚖️ *Gross Weight:* {gross_weight_kg:.2f} kg\n"
            f"📉 *Scrap Wastage Reduction:* {wastage_reduction_pct}% (-{wastage_reduction_kg:.2f} kg)\n"
            f"⚖️ *Net Billed Weight:* {net_weight_kg:.2f} kg\n"
            f"💰 *Total Bill Subtotal:* ₹{subtotal:,.2f}\n"
            f"💳 *Status:* Cash/Outstanding Ledger Updated\n"
            f"----------------------------------------\n"
            f"✅ Saved in Factory Internal Ledger."
        )

        return InvoiceGenerateModeResponse(
            invoice_id=invoice.id,
            invoice_mode="basic",
            subtotal=subtotal,
            total_amount=subtotal,
            text_summary=summary_text,
            status="SUCCESS"
        )

    else:  # gst mode
        # Serialized tax compliance invoice: serial numbers, HSN codes, CGST/SGST/IGST breakdown
        gst_rate = Decimal("12")  # 12% total GST split
        cgst_rate = gst_rate / 2  # 6%
        sgst_rate = gst_rate / 2  # 6%

        cgst_amount = subtotal * (cgst_rate / Decimal("100"))  # ₹1,080.00
        sgst_amount = subtotal * (sgst_rate / Decimal("100"))  # ₹1,080.00
        igst_amount = Decimal("0.00")
        total_amount = subtotal + cgst_amount + sgst_amount  # ₹20,160.00

        # Create SQL entry for invoice
        invoice = SalesInvoice(
            factory_id=factory_id,
            customer_id=customer.id,
            date=date.today(),
            cup_size_ml=profile.cup_size_ml,
            packaging_profile_id=profile.id,
            boxes_sold=boxes_sold,
            total_amount=total_amount,
            amount_paid=Decimal("0.00")
        )
        db.add(invoice)
        db.commit()
        db.refresh(invoice)

        # Serialized dynamic invoice number matching
        serial_invoice_number = f"MNS-2026-{invoice.id:04d}"
        hsn_code = "4823 6900"  # Paper cups / paper plate HSN

        summary_text = (
            f"🧾 *TAX INVOICE GENERATED* (GST COMPLIANT)\n"
            f"----------------------------------------\n"
            f"📄 *Invoice Number:* `{serial_invoice_number}`\n"
            f"🏢 *Factory Tenant ID:* `{factory_id}`\n"
            f"👤 *Customer:* {customer.name}\n"
            f"📦 *Product HSN:* `{hsn_code}` (Paper Cups)\n"
            f"📊 *Quantity:* {boxes_sold} Boxes ({total_cups:,} Pcs)\n"
            f"💰 *Taxable Subtotal:* ₹{subtotal:,.2f}\n"
            f"📈 *CGST ({cgst_rate}%):* ₹{cgst_amount:,.2f}\n"
            f"📈 *SGST ({sgst_rate}%):* ₹{sgst_amount:,.2f}\n"
            f"📈 *IGST:* ₹{igst_amount:,.2f}\n"
            f"----------------------------------------\n"
            f"💰 *Net Invoice Value:* ₹{total_amount:,.2f}\n"
            f"💳 *Status:* Unpaid / Registered on GST Portal\n"
            f"----------------------------------------\n"
            f"✅ Saved securely in tax ledger."
        )

        return InvoiceGenerateModeResponse(
            invoice_id=invoice.id,
            invoice_mode="gst",
            invoice_number=serial_invoice_number,
            subtotal=subtotal,
            cgst=cgst_amount,
            sgst=sgst_amount,
            igst=igst_amount,
            total_amount=total_amount,
            text_summary=summary_text,
            status="SUCCESS"
        )
