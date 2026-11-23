import asyncio

# Fake backends. Each one sleeps to feel like a real API call over the network.
ORDERS = {
    "1234": {"item": "running shoes", "status": "shipped", "arrives": "Thursday"},
    "5678": {"item": "coffee maker", "status": "processing", "arrives": "next Monday"},
}


async def get_weather(city: str):
    await asyncio.sleep(2)
    return {"city": city, "temperature_c": 31, "condition": "sunny"}


async def get_order_status(order_id: str):
    await asyncio.sleep(2)
    order = ORDERS.get(order_id.replace(" ", ""))
    if not order:
        return {"error": f"no order with id {order_id}"}
    return order


async def cancel_order(order_id: str):
    await asyncio.sleep(2)
    if order_id not in ORDERS:
        return {"error": f"no order with id {order_id}"}
    ORDERS[order_id]["status"] = "cancelled"
    return {"order_id": order_id, "status": "cancelled"}


FUNCTIONS = {"get_weather": get_weather, "get_order_status": get_order_status, "cancel_order": cancel_order}

# What the LLM sees: name, what it does, and the parameters it needs
DEFINITIONS = [
    {"type": "function", "function": {
        "name": "get_weather",
        "description": "Current weather for a city.",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
    }},
    {"type": "function", "function": {
        "name": "get_order_status",
        "description": "Look up an order by its four digit id.",
        "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
    }},
    {"type": "function", "function": {
        "name": "cancel_order",
        "description": "Cancel an order. Only call this after the user has clearly said yes to cancelling this exact order.",
        "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
    }},
]


async def run(name: str, arguments: dict):
    try:
        return await FUNCTIONS[name](**arguments)
    except Exception as e:  # the model gets a plain error to explain, never a stack trace
        return {"error": str(e)}
