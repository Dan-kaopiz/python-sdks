async def create_room(room_name: str) -> str:
    """
    Create a new chat room

    Args:
        room_name: Name of the chat room to be created

    Returns:
        Confirmation message with the room name
    """
    # Simulate room creation logic
    return f"Chat room '{room_name}' has been created successfully!"

if __name__ == "__main__":
    import asyncio

    room_name = "Test Room"
    result = asyncio.run(create_room(room_name))
    print(result)
