import os
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import scrolledtext
import platform
from anthropic import Anthropic
import pyautogui
from mss import mss
import time
from dataclasses import dataclass
from typing import List, Dict, Any

from tools import BashTool, ComputerTool, EditTool, ToolCollection
from loop import sampling_loop
from loop import APIProvider
from loop import ToolResult

# Configure logging
logging.basicConfig(
    filename='assistant.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

SYSTEM_PROMPT = f"""You are an AI assistant with access to a macOS {platform.mac_ver()[0]} environment running on {platform.machine()} architecture.

CAPABILITIES:
* You can see the current screen state through screenshots
* You can track the cursor position
* You can analyze UI elements and text on screen
* You can suggest actions for the user to take
* You can execute commands and edit files when needed
* You can help with any task the user is working on

LIMITATIONS:
* You must ask for permission before suggesting potentially destructive actions
* You should be clear about what you can and cannot see on screen

When analyzing the screen:
1. First describe what you observe
2. Then suggest relevant actions based on the user's query
3. Ask for clarification if needed

Format your responses as clear, actionable suggestions."""

@dataclass
class UIAction:
    """Represents a single UI interaction"""
    action_type: str  # click, type, move, etc.
    screen_before: Dict[str, Any]  # Screen state before action
    screen_after: Dict[str, Any]   # Screen state after action
    coordinates: tuple[int, int] | None  # Mouse coordinates if applicable
    text_input: str | None         # Text input if applicable
    description: str               # User description of action
    analysis: str | None           # AI analysis of the action

class AIAssistant:
    def __init__(self, output_callback):
        """Initialize the AI Assistant with Anthropic's Claude."""
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.screen = mss()
        self.output_callback = output_callback
        self.tools = ToolCollection(
            ComputerTool(),
            BashTool(),
            EditTool(),
        )
        self.messages = []
        
    async def get_screen_state(self):
        """Capture current screen state."""
        screenshot = self.screen.grab(self.screen.monitors[0])
        cursor_x, cursor_y = pyautogui.position()
        
        return {
            "screenshot": screenshot,
            "cursor_position": (cursor_x, cursor_y),
            "screen_size": (screenshot.width, screenshot.height)
        }
        
    async def analyze_and_act(self, screen_state, user_query):
        """Analyze screen state and user query with Claude."""
        try:
            logging.info(f"Processing query: {user_query}")
            screen_desc = f"Screen size: {screen_state['screen_size']}, Cursor at: {screen_state['cursor_position']}"
            
            # Add user message to history
            self.messages.append({
                "role": "user",
                "content": [{
                    "type": "text",
                    "text": f"Current screen state: {screen_desc}\n\nUser query: {user_query}"
                }]
            })
            
            # Run the sampling loop
            await sampling_loop(
                model="claude-3-5-sonnet-20241022",
                provider=APIProvider.ANTHROPIC,
                system_prompt_suffix="",
                messages=self.messages,
                output_callback=self._handle_output,
                tool_output_callback=self._handle_tool_output,
                api_response_callback=self._handle_api_response,
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                max_tokens=4096
            )
            
            return "Processing complete"
            
        except Exception as e:
            error_msg = f"Error in analyze_and_act: {str(e)}"
            logging.error(error_msg)
            return error_msg

    def _handle_output(self, content_block):
        """Handle output from Claude"""
        if content_block["type"] == "text":
            self.output_callback(f"\nAssistant: {content_block['text']}")
            
    def _handle_tool_output(self, result: ToolResult, tool_id: str):
        """Handle tool execution results"""
        if result.output:
            self.output_callback(f"\nTool output: {result.output}")
        if result.error:
            self.output_callback(f"\nTool error: {result.error}")
            
    def _handle_api_response(self, request, response, error):
        """Handle API responses for logging"""
        if error:
            logging.error(f"API error: {error}")
        else:
            logging.info("API request successful")

class ActionRecorder:
    """Records and analyzes user actions on the UI"""
    def __init__(self, assistant: "AIAssistant"):  # Using string literal type annotation
        self.assistant = assistant
        self.recording = False
        self.actions: List[UIAction] = []
        self.current_app = ""
        
    async def start_recording(self, app_name: str):
        """Start recording user actions for a specific application"""
        self.recording = True
        self.current_app = app_name
        self.actions = []
        
    def stop_recording(self):
        """Stop recording and save the workflow"""
        self.recording = False
        self._save_workflow()
        
    async def record_action(self, action_type: str, coordinates: tuple[int, int] | None = None, 
                          text: str | None = None, description: str = ""):
        """Record a single user action with before/after screen states"""
        if not self.recording:
            return
            
        # Capture screen state before action
        screen_before = await self.assistant.get_screen_state()
        
        # Wait briefly for any UI updates
        await asyncio.sleep(0.5)
        
        # Capture screen state after action
        screen_after = await self.assistant.get_screen_state()
        
        # Get AI analysis of the action
        analysis = await self._analyze_action(screen_before, screen_after, action_type, description)
        
        action = UIAction(
            action_type=action_type,
            screen_before=screen_before,
            screen_after=screen_after,
            coordinates=coordinates,
            text_input=text,
            description=description,
            analysis=analysis
        )
        
        self.actions.append(action)
        
    async def _analyze_action(self, before: Dict, after: Dict, action_type: str, description: str) -> str:
        """Have the AI analyze what changed between screen states"""
        analysis_query = f"""Analyze this UI interaction in {self.current_app}:
        Action type: {action_type}
        User description: {description}
        
        What changed on screen?
        What was the likely purpose of this action?
        What UI elements were involved?"""
        
        response = await self.assistant.analyze_and_act(before, analysis_query)
        return response
        
    def _save_workflow(self):
        """Save the recorded workflow to a JSON file"""
        workflow = {
            "app": self.current_app,
            "timestamp": datetime.now().isoformat(),
            "actions": [
                {
                    "type": a.action_type,
                    "description": a.description,
                    "analysis": a.analysis,
                    "coordinates": a.coordinates,
                    "text": a.text_input
                }
                for a in self.actions
            ]
        }
        
        path = Path(f"workflows/{self.current_app}_{int(time.time())}.json")
        path.parent.mkdir(exist_ok=True)
        
        with open(path, "w") as f:
            json.dump(workflow, f, indent=2)

class AssistantUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AI Assistant")
        self.root.attributes('-topmost', True)  # Keep window on top
        self.root.geometry('400x600')  # Set initial size
        
        # Initialize AI Assistant and Recorder
        self.assistant = AIAssistant(self.append_to_output)
        self.recorder = ActionRecorder(self.assistant)
        
        # Create and configure UI elements
        self.create_widgets()
        
    def create_widgets(self):
        # Recording controls
        self.recording_frame = tk.Frame(self.root)
        self.recording_frame.pack(padx=10, pady=5, fill=tk.X)
        
        self.app_entry = tk.Entry(self.recording_frame)
        self.app_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.app_entry.insert(0, "Enter app name...")
        
        self.record_btn = tk.Button(self.recording_frame, text="Start Recording", 
                                  command=self.toggle_recording)
        self.record_btn.pack(side=tk.RIGHT, padx=5)
        
        # Action description
        self.action_frame = tk.Frame(self.root)
        self.action_frame.pack(padx=10, pady=5, fill=tk.X)
        
        self.action_entry = tk.Entry(self.action_frame)
        self.action_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.action_entry.insert(0, "Describe your action...")
        
        self.action_btn = tk.Button(self.action_frame, text="Record Action",
                                  command=self.record_current_action)
        self.action_btn.pack(side=tk.RIGHT, padx=5)
        
        # Output area
        self.output_area = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, height=30)
        self.output_area.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        
        # Input area
        self.input_frame = tk.Frame(self.root)
        self.input_frame.pack(padx=10, pady=5, fill=tk.X)
        
        self.input_field = tk.Entry(self.input_frame)
        self.input_field.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.input_field.bind('<Return>', self.process_input)
        
        self.submit_btn = tk.Button(self.input_frame, text="Ask", command=self.process_input)
        self.submit_btn.pack(side=tk.RIGHT, padx=5)
        
    def append_to_output(self, text):
        self.output_area.insert(tk.END, f"\n{text}")
        self.output_area.see(tk.END)
        
    def process_input(self, event=None):
        query = self.input_field.get()
        if not query:
            return
            
        self.input_field.delete(0, tk.END)
        self.append_to_output(f"\nYou: {query}")
        
        # Process query asynchronously
        asyncio.create_task(self.handle_query(query))
        
    async def handle_query(self, query):
        screen_state = await self.assistant.get_screen_state()
        response = await self.assistant.analyze_and_act(screen_state, query)
        self.append_to_output(f"\nAssistant: {response}")
        
    async def toggle_recording(self):
        if not self.recorder.recording:
            app_name = self.app_entry.get()
            if app_name and app_name != "Enter app name...":
                await self.recorder.start_recording(app_name)
                self.record_btn.config(text="Stop Recording")
                self.append_to_output(f"\nStarted recording actions for {app_name}")
        else:
            self.recorder.stop_recording()
            self.record_btn.config(text="Start Recording")
            self.append_to_output("\nStopped recording. Workflow saved.")
            
    async def record_current_action(self):
        if self.recorder.recording:
            description = self.action_entry.get()
            if description and description != "Describe your action...":
                # Get current mouse position
                x, y = pyautogui.position()
                await self.recorder.record_action("manual", (x, y), None, description)
                self.append_to_output(f"\nRecorded action: {description}")
                self.action_entry.delete(0, tk.END)
                self.action_entry.insert(0, "Describe your action...")
        
    def run(self):
        # Create async event loop
        async def async_mainloop():
            while True:
                self.root.update()
                await asyncio.sleep(0.1)
                
        asyncio.run(async_mainloop())

def main():
    ui = AssistantUI()
    ui.run()

if __name__ == "__main__":
    main() 