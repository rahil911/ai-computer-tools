import asyncio
import base64
import os
from pathlib import Path
import time

from tools import BashTool, ComputerTool, EditTool, ToolCollection


def verify_base64_image(base64_str: str | None) -> bool:
    """Verify that the string is a valid base64-encoded PNG image."""
    if not base64_str:
        return False
    try:
        # Decode base64
        image_data = base64.b64decode(base64_str)
        # Check PNG signature
        return image_data.startswith(b'\x89PNG\r\n\x1a\n')
    except Exception:
        return False


async def test_screenshot_tool(tools: ToolCollection):
    """Test screenshot functionality in detail"""
    print("\n=== Testing Screenshot Capabilities ===")
    
    # 1. Basic screenshot
    print("\n1. Testing basic screenshot...")
    result = await tools.run(
        name="computer",
        tool_input={"action": "screenshot"}
    )
    if not result.base64_image:
        print("❌ Screenshot failed - no base64 image data")
        return False
    
    if not verify_base64_image(result.base64_image):
        print("❌ Screenshot failed - invalid PNG data")
        return False
        
    print("✅ Screenshot successful - valid PNG image data")
    print(f"Image data length: {len(result.base64_image)} bytes")
    
    # 2. Save screenshot to verify
    print("\n2. Saving screenshot to file for verification...")
    test_file = Path("test_screenshot.png")
    try:
        with open(test_file, "wb") as f:
            f.write(base64.b64decode(result.base64_image))
        print(f"✅ Screenshot saved to {test_file}")
        print(f"File size: {test_file.stat().st_size} bytes")
    except Exception as e:
        print(f"❌ Failed to save screenshot: {e}")
    finally:
        if test_file.exists():
            test_file.unlink()
    
    return True


async def test_computer_tool(tools: ToolCollection):
    """Test all computer tool actions"""
    print("\n=== Testing Computer Tool ===")
    
    # Test screenshot first
    if not await test_screenshot_tool(tools):
        raise Exception("Screenshot functionality failed")
    
    # 1. Get initial cursor position
    print("\n1. Testing cursor position...")
    result = await tools.run(
        name="computer",
        tool_input={"action": "cursor_position"}
    )
    print(f"Initial cursor position: {result.output}")
    initial_pos = result.output
    
    # 2. Move mouse
    print("\n2. Testing mouse movement...")
    await tools.run(
        name="computer",
        tool_input={
            "action": "mouse_move",
            "coordinate": [100, 100]
        }
    )
    print("Moved mouse to (100, 100)")
    
    # 3. Take screenshot
    print("\n3. Testing screenshot...")
    result = await tools.run(
        name="computer",
        tool_input={"action": "screenshot"}
    )
    print("Screenshot taken" if result.base64_image else "Screenshot failed")
    
    # 4. Type text
    print("\n4. Testing typing...")
    test_file = Path("typing_test.txt")
    # First create a file to type into
    await tools.run(
        name="str_replace_editor",
        tool_input={
            "command": "create",
            "path": str(test_file.absolute()),
            "file_text": ""
        }
    )
    # Open the file in default text editor
    await tools.run(
        name="bash",
        tool_input={"command": f"open {test_file}"}
    )
    time.sleep(2)  # Wait for editor to open
    
    await tools.run(
        name="computer",
        tool_input={
            "action": "type",
            "text": "Hello from computer tool!"
        }
    )
    print("Typed text into editor")
    
    # 5. Press keys
    print("\n5. Testing key press...")
    await tools.run(
        name="computer",
        tool_input={
            "action": "key",
            "text": "enter"
        }
    )
    print("Pressed enter key")
    
    # 6. Mouse clicks
    print("\n6. Testing mouse clicks...")
    # Left click
    await tools.run(
        name="computer",
        tool_input={"action": "left_click"}
    )
    print("Left click performed")
    
    # Right click
    await tools.run(
        name="computer",
        tool_input={"action": "right_click"}
    )
    print("Right click performed")
    
    # Double click
    await tools.run(
        name="computer",
        tool_input={"action": "double_click"}
    )
    print("Double click performed")
    
    # 7. Drag operation
    print("\n7. Testing mouse drag...")
    await tools.run(
        name="computer",
        tool_input={
            "action": "left_click_drag",
            "coordinate": [200, 200]
        }
    )
    print("Drag operation performed")
    
    # Clean up
    if test_file.exists():
        test_file.unlink()
    
    # Return to initial position
    if initial_pos:
        x, y = map(int, initial_pos.replace("X=", "").replace("Y=", "").split(","))
        await tools.run(
            name="computer",
            tool_input={
                "action": "mouse_move",
                "coordinate": [x, y]
            }
        )


async def test_bash_tool(tools: ToolCollection):
    """Test bash tool capabilities"""
    print("\n=== Testing Bash Tool ===")
    
    # 1. Basic command
    print("\n1. Testing basic command...")
    result = await tools.run(
        name="bash",
        tool_input={"command": "echo 'Hello from bash!'"}
    )
    print(f"Basic command output: {result.output}")
    
    # 2. Directory operations
    print("\n2. Testing directory operations...")
    result = await tools.run(
        name="bash",
        tool_input={"command": "pwd && ls -la"}
    )
    print(f"Directory listing: {result.output}")
    
    # 3. Environment variables
    print("\n3. Testing environment variables...")
    result = await tools.run(
        name="bash",
        tool_input={"command": "echo $PATH"}
    )
    print(f"PATH: {result.output}")
    
    # 4. Command chaining
    print("\n4. Testing command chaining...")
    result = await tools.run(
        name="bash",
        tool_input={"command": "mkdir -p test_dir && cd test_dir && pwd && cd .. && rm -r test_dir"}
    )
    print(f"Chained commands output: {result.output}")


async def test_edit_tool(tools: ToolCollection):
    """Test edit tool capabilities"""
    print("\n=== Testing Edit Tool ===")
    test_file = Path("edit_test.txt")
    
    # 1. Create file
    print("\n1. Testing file creation...")
    result = await tools.run(
        name="str_replace_editor",
        tool_input={
            "command": "create",
            "path": str(test_file.absolute()),
            "file_text": "Line 1\nLine 2\nLine 3"
        }
    )
    print(f"Create result: {result.output}")
    
    # 2. View file
    print("\n2. Testing file view...")
    result = await tools.run(
        name="str_replace_editor",
        tool_input={
            "command": "view",
            "path": str(test_file.absolute())
        }
    )
    print(f"View result: {result.output}")
    
    # 3. String replace
    print("\n3. Testing string replace...")
    result = await tools.run(
        name="str_replace_editor",
        tool_input={
            "command": "str_replace",
            "path": str(test_file.absolute()),
            "old_str": "Line 2",
            "new_str": "Modified Line 2"
        }
    )
    print(f"Replace result: {result.output}")
    
    # 4. Insert
    print("\n4. Testing line insertion...")
    result = await tools.run(
        name="str_replace_editor",
        tool_input={
            "command": "insert",
            "path": str(test_file.absolute()),
            "insert_line": 2,
            "new_str": "Inserted Line"
        }
    )
    print(f"Insert result: {result.output}")
    
    # 5. Undo
    print("\n5. Testing undo...")
    result = await tools.run(
        name="str_replace_editor",
        tool_input={
            "command": "undo_edit",
            "path": str(test_file.absolute())
        }
    )
    print(f"Undo result: {result.output}")
    
    # Clean up
    if test_file.exists():
        test_file.unlink()


async def test_tools():
    """Run all tool tests"""
    print("Starting comprehensive tool tests...")
    
    tools = ToolCollection(
        ComputerTool(),
        BashTool(),
        EditTool(),
    )
    
    try:
        await test_computer_tool(tools)
        await test_bash_tool(tools)
        await test_edit_tool(tools)
        print("\n✅ All tools tested successfully!")
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")


if __name__ == "__main__":
    asyncio.run(test_tools()) 