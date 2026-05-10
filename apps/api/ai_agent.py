import os
import re
from types import UnionType
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, TypeVar, Union, get_args, get_origin

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

try:
    from langchain.memory import ConversationBufferMemory
except ImportError:  # LangChain 1.x compatibility
    try:
        from langchain_classic.memory import ConversationBufferMemory
    except ImportError:
        class ConversationBufferMemory:
            def __init__(self, memory_key: str, input_key: str, output_key: str):
                self.memory_key = memory_key
                self.input_key = input_key
                self.output_key = output_key
                self.buffer: List[Tuple[str, str]] = []

            def load_memory_variables(self, _inputs):
                chat_history = "\n".join(
                    f"Human: {human_message}\nAI: {ai_message}"
                    for human_message, ai_message in self.buffer[-10:]
                )
                return {self.memory_key: chat_history}

            def save_context(self, inputs, outputs):
                self.buffer.append(
                    (
                        str(inputs.get(self.input_key, "")),
                        str(outputs.get(self.output_key, "")),
                    )
                )

try:
    from langchain_groq import ChatGroq
except ImportError:
    ChatGroq = None


IntentModel = TypeVar("IntentModel")

SESSION_MEMORIES: Dict[str, ConversationBufferMemory] = {}
PENDING_PRODUCTION_FORMS: Dict[str, Any] = {}


def get_session_memory(session_id: str) -> ConversationBufferMemory:
    if session_id not in SESSION_MEMORIES:
        SESSION_MEMORIES[session_id] = ConversationBufferMemory(
            memory_key="chat_history",
            input_key="user_message",
            output_key="ai_reply",
        )
    return SESSION_MEMORIES[session_id]


def initialize_groq_llm():
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key or ChatGroq is None:
        return None

    try:
        return ChatGroq(
            model=os.getenv("GROQ_MODEL") or "llama-3.1-8b-instant",
            temperature=0,
            api_key=groq_api_key,
        )
    except Exception:
        return None


def build_factory_supervisor_prompt(parser: PydanticOutputParser) -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
            "You are the Factory Supervisor. You have access to real-time database tools: "
            "get_inventory, get_customers, and get_factory_machines. These tools are already bound to the logged-in factory_id. "
            "If a user asks \"65ml ka kitna mal pada hai?\", call/use the inventory context first, then reply in Hindi/Hinglish.\n"
            "You are a friendly and intelligent Factory Supervisor Assistant for a paper cup factory ERP.\n"
            "Factory owners type messy natural language. Be forgiving and conversational.\n"
            "Extract structured data when enough information is present, but never invent missing facts.\n\n"
            "Tone and fallback rules:\n"
            "- Always speak respectfully, like a loyal manager helping the factory owner.\n"
            "- If the user writes in Hindi or Hinglish, reply in natural Hindi/Hinglish.\n"
            "- If you cannot understand the intent, or the request is unrelated to factory operations, never say "
            "\"I don't know\" and never produce a blunt refusal.\n"
            "- Instead, politely say you did not quite catch it and remind the user what you can help with: "
            "production logs, stock checks, sale records, expenses, employee attendance/overtime/advance, and customer balances.\n"
            "- In every unclear/out-of-scope reply, include 2-3 concrete copyable examples the user can ask, such as:\n"
            '  1. Aap production log kar sakte hain: "Aaj 200ml cup ke 50 box bane".\n'
            '  2. Aap stock check kar sakte hain: "210ml ka kitna stock bacha hai?"\n'
            '  3. Aap sale record kar sakte hain: "Ram ko 10 box 65ml bech do".\n'
            "- Keep fallback answers short, useful, and guiding. Do not expose parser, schema, or system details.\n\n"
            "Classify the newest message as exactly one of: production_entry, sales_entry, expense_entry, "
            "employee_entry, general_qa.\n"
            "You can request one of these backend tools by setting tool_name and tool_args:\n"
            "- check_inventory(product_name): answer current stock.\n"
            "- record_sale(customer_name, product, quantity): deduct stock and create a sales entry.\n"
            "- log_production(product, quantity): add production to stock.\n"
            "Use the Product List below to match fuzzy product names before choosing a tool.\n\n"
            "Real-time database tool context for this factory:\n{tool_context}\n\n"
            "Production logging uses loose form filling. Quantity/boxes produced is the most important field. "
            "Product name, cup size, packing profile, raw material used, machine speed, blank waste, bottom waste, "
            "and general wastage are optional and should be null or 0 when not mentioned.\n"
            "If the user starts a production log but misses a crucial detail like cup size/product, extract whatever "
            "you can; the API will ask a friendly follow-up instead of throwing a validation error.\n"
            "If the user is answering a previous follow-up, use chat history to connect the answer to the pending log.\n\n"
            "Examples:\n"
            '- "we made 50 boxes today" means production_entry with quantity=50 and boxes_produced=50; unknown fields null/0.\n'
            '- If the next message is "200ml", connect it to the previous 50 boxes and set cup_size_ml=200.\n'
            '- "50 boxes 65ml premium packing" means production_entry with quantity=50, boxes_produced=50, '
            'product_name="65ml Paper Cup", cup_size_ml=65, packing_profile_name="65ml Premium Packing".\n'
            "For general_qa, put a short friendly natural-language reply in general_data.answer. "
            "If it is unclear or out of scope, use the graceful fallback rules and include valid query examples.\n\n"
            "Product List for this factory:\n{product_catalog}\n\n"
            "{format_instructions}"
            ),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{user_message}"),
        ]
    ).partial(format_instructions=parser.get_format_instructions())


def parse_factory_intent_with_agent(
    message: str,
    session_id: str,
    intent_model: Type[IntentModel],
    fallback_parser: Callable[[str], IntentModel],
    product_catalog: str = "",
    chat_history: Optional[List[Dict[str, str]]] = None,
    tool_context: str = "",
) -> Tuple[IntentModel, bool]:
    raw_intent, used_llm = _parse_with_llm_or_fallback(
        message,
        session_id,
        intent_model,
        fallback_parser,
        product_catalog,
        chat_history,
        tool_context,
    )
    return _apply_conversational_form_filling(
        message=message,
        session_id=session_id,
        intent=raw_intent,
        intent_model=intent_model,
        fallback_parser=fallback_parser,
    ), used_llm


def save_agent_context(session_id: str, user_message: str, ai_reply: str) -> None:
    memory = get_session_memory(session_id)
    memory.save_context({"user_message": user_message}, {"ai_reply": ai_reply})


def _parse_with_llm_or_fallback(
    message: str,
    session_id: str,
    intent_model: Type[IntentModel],
    fallback_parser: Callable[[str], IntentModel],
    product_catalog: str,
    chat_history: Optional[List[Dict[str, str]]],
    tool_context: str,
) -> Tuple[IntentModel, bool]:
    memory_messages = normalize_chat_history(chat_history)
    if not memory_messages:
        memory_messages = legacy_memory_to_messages(session_id)
    llm = initialize_groq_llm()

    if llm is None:
        return fallback_parser(message), False

    try:
        parser = PydanticOutputParser(pydantic_object=intent_model)
        prompt = build_factory_supervisor_prompt(parser)
        chain = prompt | llm | parser
        return chain.invoke(
            {
                "chat_history": memory_messages[-10:],
                "product_catalog": product_catalog or "No products configured yet.",
                "tool_context": tool_context or "No live database context loaded yet.",
                "user_message": message,
            }
        ), True
    except Exception:
        return fallback_parser(message), False


def _apply_conversational_form_filling(
    message: str,
    session_id: str,
    intent: IntentModel,
    intent_model: Type[IntentModel],
    fallback_parser: Callable[[str], IntentModel],
) -> IntentModel:
    completed_pending = _try_complete_pending_production(message, session_id, intent)
    if completed_pending is not None:
        return completed_pending

    production_intent = intent if _is_production_intent(intent) else fallback_parser(message)
    if not _is_production_intent(production_intent):
        return intent

    production_data = getattr(production_intent, "production_data", None)
    quantity = _production_quantity(production_data)
    has_product_context = _has_product_context(production_data)

    if not quantity:
        PENDING_PRODUCTION_FORMS[session_id] = production_intent
        return _make_general_followup(
            intent_model,
            message,
            "Got it, you want to log production. How many boxes did you make?",
        )

    if not has_product_context:
        PENDING_PRODUCTION_FORMS[session_id] = production_intent
        return _make_general_followup(
            intent_model,
            message,
            f"Got it, {quantity} boxes. Which cup size or product did you make?",
        )

    PENDING_PRODUCTION_FORMS.pop(session_id, None)
    return production_intent


def _try_complete_pending_production(message: str, session_id: str, intent: IntentModel) -> Optional[IntentModel]:
    pending_intent = PENDING_PRODUCTION_FORMS.get(session_id)
    if pending_intent is None:
        return None

    pending_data = getattr(pending_intent, "production_data", None)
    current_data = getattr(intent, "production_data", None)
    cup_size = _field(current_data, "cup_size_ml") or _extract_cup_size_ml(message)
    product_name = _field(current_data, "product_name")
    packing_profile_name = _field(current_data, "packing_profile_name")
    quantity = _production_quantity(current_data)

    if cup_size:
        _set_field(pending_data, "cup_size_ml", cup_size)
        if not _field(pending_data, "product_name"):
            _set_field(pending_data, "product_name", f"{cup_size}ml Paper Cup")
    if product_name:
        _set_field(pending_data, "product_name", product_name)
    if packing_profile_name:
        _set_field(pending_data, "packing_profile_name", packing_profile_name)
    if quantity and not _production_quantity(pending_data):
        _set_field(pending_data, "quantity", quantity)
        _set_field(pending_data, "boxes_produced", quantity)

    if _production_quantity(pending_data) and _has_product_context(pending_data):
        PENDING_PRODUCTION_FORMS.pop(session_id, None)
        return pending_intent

    return None


def normalize_chat_history(chat_history: Optional[List[Dict[str, str]]]) -> List[BaseMessage]:
    if not chat_history:
        return []

    messages: List[BaseMessage] = []
    for item in chat_history[-10:]:
        role = item.get("role")
        content = item.get("content")
        if not content:
            continue
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    return messages


def legacy_memory_to_messages(session_id: str) -> List[BaseMessage]:
    memory = get_session_memory(session_id)
    raw_history = memory.load_memory_variables({}).get("chat_history", "")
    if not raw_history:
        return []

    messages: List[BaseMessage] = []
    for block in str(raw_history).splitlines():
        if block.startswith("Human: "):
            messages.append(HumanMessage(content=block.removeprefix("Human: ")))
        elif block.startswith("AI: "):
            messages.append(AIMessage(content=block.removeprefix("AI: ")))
    return messages[-10:]


def _make_general_followup(intent_model: Type[IntentModel], question: str, answer: str) -> IntentModel:
    general_model = _nested_model(intent_model, "general_data")
    general_data = general_model(question=question, answer=answer) if general_model else {"question": question, "answer": answer}
    return intent_model(intent_type="general_qa", general_data=general_data)


def _nested_model(intent_model: Type[IntentModel], field_name: str):
    model_fields = getattr(intent_model, "model_fields", {})
    field = model_fields.get(field_name)
    if field is None:
        return None
    annotation = field.annotation
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        for arg in get_args(annotation):
            if arg is not type(None):
                return arg
    return annotation


def _is_production_intent(intent: Any) -> bool:
    intent_type = getattr(intent, "intent_type", None)
    return getattr(intent_type, "value", intent_type) == "production_entry"


def _production_quantity(production_data: Any) -> Optional[int]:
    return _field(production_data, "boxes_produced") or _field(production_data, "quantity")


def _has_product_context(production_data: Any) -> bool:
    return bool(
        _field(production_data, "cup_size_ml")
        or _field(production_data, "product_name")
        or _field(production_data, "packing_profile_name")
    )


def _field(model: Any, field_name: str):
    if model is None:
        return None
    if isinstance(model, dict):
        return model.get(field_name)
    return getattr(model, field_name, None)


def _set_field(model: Any, field_name: str, value) -> None:
    if model is None or value is None:
        return
    if isinstance(model, dict):
        model[field_name] = value
        return
    if hasattr(model, field_name):
        setattr(model, field_name, value)


def _extract_cup_size_ml(message: str) -> Optional[int]:
    match = re.search(r"\b(\d{2,4})\s*ml\b", message, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))

    stripped = message.strip()
    if re.fullmatch(r"\d{2,4}", stripped):
        return int(stripped)

    return None


def get_inventory_status(db: Any, factory_id: int) -> Dict[str, Any]:
    from models import BlankStock, BottomStock, BoxStock, FinalProductStock, Inventory

    return {
        "inventory": [
            {
                "item_name": item.item_name,
                "category": item.category,
                "quantity": float(item.quantity or 0),
                "unit": item.unit,
            }
            for item in db.query(Inventory).filter(Inventory.factory_id == factory_id).order_by(Inventory.item_name.asc()).all()
        ],
        "blank_stock": [
            {
                "blank_size_ml": stock.blank_size_ml,
                "linked_bottom_size_mm": stock.linked_bottom_size_mm,
                "total_qty_kg": float(stock.total_qty_kg or 0),
            }
            for stock in db.query(BlankStock).filter(BlankStock.factory_id == factory_id).order_by(BlankStock.blank_size_ml.asc()).all()
        ],
        "bottom_stock": [
            {
                "bottom_size_mm": stock.bottom_size_mm,
                "total_qty_kg": float(stock.total_qty_kg or 0),
            }
            for stock in db.query(BottomStock).filter(BottomStock.factory_id == factory_id).order_by(BottomStock.bottom_size_mm.asc()).all()
        ],
        "box_stock": [
            {
                "packaging_size_name": stock.packaging_size_name,
                "total_boxes": int(stock.total_boxes or 0),
            }
            for stock in db.query(BoxStock).filter(BoxStock.factory_id == factory_id).order_by(BoxStock.packaging_size_name.asc()).all()
        ],
        "final_product_stock": [
            {
                "product_size_ml": stock.product_size_ml,
                "packaging_size_name": stock.packaging_size_name,
                "total_boxes": int(stock.total_boxes or 0),
                "loose_packets": int(stock.loose_packets or 0),
                "packets_per_box_limit": stock.packets_per_box_limit,
            }
            for stock in db.query(FinalProductStock).filter(FinalProductStock.factory_id == factory_id).order_by(FinalProductStock.product_size_ml.asc()).all()
        ],
    }


def get_inventory(db: Any, factory_id: int) -> Dict[str, Any]:
    return get_inventory_status(db, factory_id)


def get_customer_ledger(db: Any, factory_id: int, name: str = "") -> Dict[str, Any]:
    from sqlalchemy import func as sql_func
    from models import Customer

    query = db.query(Customer).filter(Customer.factory_id == factory_id)
    if name:
        query = query.filter(sql_func.lower(Customer.name).like(f"%{name.lower()}%"))
    return {
        "customers": [
            {
                "id": customer.id,
                "name": customer.name,
                "phone": customer.phone or customer.contact_number,
                "previous_due": float(customer.previous_due or 0),
                "total_due": float(customer.total_due or customer.balance_amount or 0),
            }
            for customer in query.order_by(Customer.name.asc()).limit(20).all()
        ]
    }


def get_customers(db: Any, factory_id: int, name: str = "") -> Dict[str, Any]:
    return get_customer_ledger(db, factory_id, name)


def get_factory_config(db: Any, factory_id: int) -> Dict[str, Any]:
    from models import Machine, PackagingMetrics, RawMaterialMetrics

    raw_metrics = db.query(RawMaterialMetrics).filter(RawMaterialMetrics.factory_id == factory_id).all()
    return {
        "machines": [
            {
                "id": machine.id,
                "machine_number": machine.machine_number or machine.machine_sequence_number or machine.name,
                "machine_type": machine.machine_type,
                "cup_size_ml": machine.mould_size_ml or machine.cup_size_ml,
                "bottom_size_mm": machine.bottom_size_mm,
                "speed_per_minute": machine.speed_per_minute,
            }
            for machine in db.query(Machine).filter(Machine.factory_id == factory_id).order_by(Machine.id.asc()).all()
        ],
        "raw_material_metrics": [
            {
                "material_type": metric.material_type,
                "size_ml_or_mm": metric.size_ml_or_mm,
                "weight_per_sack_kg": float(metric.weight_per_sack_kg or 0),
                "pieces_per_sack": metric.pieces_per_sack,
                "pieces_per_kg": (
                    float(metric.pieces_per_sack) / float(metric.weight_per_sack_kg)
                    if metric.weight_per_sack_kg
                    else 0
                ),
            }
            for metric in raw_metrics
        ],
        "packaging_metrics": [
            {
                "cup_size_ml": metric.cup_size_ml,
                "kg_per_box": float(metric.kg_per_box or 0),
                "cups_per_box": metric.cups_per_box,
            }
            for metric in db.query(PackagingMetrics).filter(PackagingMetrics.factory_id == factory_id).order_by(PackagingMetrics.cup_size_ml.asc()).all()
        ],
    }


def get_factory_machines(db: Any, factory_id: int) -> Dict[str, Any]:
    return {"machines": get_factory_config(db, factory_id).get("machines", [])}


def build_ai_tool_context(db: Any, factory_id: int, customer_name: str = "") -> str:
    context = {
        "factory_id": factory_id,
        "bound_tools": ["get_inventory", "get_customers", "get_factory_machines"],
        "inventory_status": get_inventory(db, factory_id),
        "customer_ledger": get_customers(db, factory_id, customer_name),
        "factory_config": get_factory_config(db, factory_id),
    }
    return str(context)[:12000]
