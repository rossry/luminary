#!/usr/bin/env python3
"""FastAPI server for real-time pattern animation streaming.

This server provides both HTTP endpoints for serving static files and WebSocket
endpoints for streaming animated pattern data to web clients.
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Dict, Set, Optional
import argparse

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn

# Import luminary modules
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from luminary.config import JSONLoader
from luminary.geometry.net import Net
from luminary.patterns.beam_array import BeamArrayBuilder
from luminary.patterns.discovery import get_pattern_or_select, discover_patterns


class PatternAnimationServer:
    """WebSocket server for streaming pattern animation data."""
    
    def __init__(self, net: Net, pattern, fps: float = 30.0):
        self.net = net
        self.pattern = pattern
        self.fps = fps
        self.frame_interval = 1.0 / fps
        self.start_time = None
        self.connected_clients: Set[WebSocket] = set()
        self.beam_array_builder = BeamArrayBuilder(net)
        self.beam_array = None
        self.running = False
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        # Cache SVG structure
        self._svg_structure = None
    
    def get_svg_structure(self) -> str:
        """Get the base SVG structure (cached)."""
        if self._svg_structure is None:
            svg_elements = self.net.get_svg(extended=True)
            self._svg_structure = "".join(svg_elements)
        return self._svg_structure
    
    async def register_client(self, websocket: WebSocket):
        """Register a new client connection."""
        await websocket.accept()
        self.connected_clients.add(websocket)
        self.logger.info(f"Client connected. Total clients: {len(self.connected_clients)}")
        
        # Send initial SVG structure to client
        await self.send_svg_structure(websocket)
        
        # If animation not running and we have clients, start it
        if not self.running and len(self.connected_clients) > 0:
            await self.start_animation()
    
    def unregister_client(self, websocket: WebSocket):
        """Unregister a client connection."""
        self.connected_clients.discard(websocket)
        self.logger.info(f"Client disconnected. Total clients: {len(self.connected_clients)}")
        
        # Stop animation if no clients
        if len(self.connected_clients) == 0:
            self.stop_animation()
    
    async def send_svg_structure(self, websocket: WebSocket):
        """Send the base SVG structure to a newly connected client."""
        try:
            message = {
                "type": "svg_structure",
                "content": self.get_svg_structure()
            }
            
            await websocket.send_text(json.dumps(message))
            self.logger.debug("Sent SVG structure to client")
            
        except Exception as e:
            self.logger.error(f"Error sending SVG structure: {e}")
    
    def generate_frame(self, t: float) -> Dict[str, list]:
        """Generate a frame of pattern data at time t.
        
        Returns:
            Dictionary mapping colon-separated beam IDs to OKLCH arrays [l, c, h].
        """
        if self.beam_array is None:
            self.beam_array = self.beam_array_builder.build_array()
            # Pre-compute beam ID strings for performance
            self.beam_id_strings = {}
            beam_idx = 0
            for face_idx, triangle in enumerate(self.beam_array_builder.net.triangles):
                actual_face_idx = triangle.triangle_id
                for facet_idx, facet in enumerate(triangle.facets):
                    beam_groups = facet.get_beams()
                    for edge_idx, edge_beams in enumerate(beam_groups):
                        for position_idx, beam in enumerate(edge_beams):
                            if beam_idx < len(self.beam_array):
                                beam_id = (actual_face_idx, facet_idx, edge_idx, position_idx)
                                beam_id_str = f"{beam_id[0]}:{beam_id[1]}:{beam_id[2]}:{beam_id[3]}"
                                self.beam_id_strings[beam_idx] = beam_id_str
                                beam_idx += 1
        
        # Evaluate pattern at time t
        oklch_values = self.pattern.evaluate(self.beam_array, t)
        
        # Convert to framebuffer format - send raw OKLCH arrays for client-side formatting
        framebuffer = {}
        for beam_idx in range(len(oklch_values)):
            l, c, h = oklch_values[beam_idx]
            beam_id_str = self.beam_id_strings[beam_idx]
            # Send raw OKLCH values as array - much faster than string formatting
            framebuffer[beam_id_str] = [float(l), float(c), float(h)]
        
        return framebuffer
    
    async def broadcast_frame(self, framebuffer: Dict[str, list]):
        """Broadcast frame data to all connected clients."""
        if not self.connected_clients:
            return
        
        message = {
            "type": "framebuffer",
            "data": framebuffer,
            "timestamp": time.time()
        }
        
        message_json = json.dumps(message)
        
        # Send to all clients concurrently to avoid blocking on slow clients
        clients_list = list(self.connected_clients.copy())
        send_tasks = []
        for client in clients_list:
            task = asyncio.create_task(self._send_to_client(client, message_json))
            send_tasks.append(task)
        
        # Wait for all sends to complete (or timeout/fail)
        if send_tasks:
            results = await asyncio.gather(*send_tasks, return_exceptions=True)
            
            # Remove clients that failed to receive the message
            disconnected_clients = set()
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    if i < len(clients_list):
                        client = clients_list[i]
                        self.logger.error(f"Error sending to client: {result}")
                        disconnected_clients.add(client)
            
            for client in disconnected_clients:
                self.unregister_client(client)
    
    async def _send_to_client(self, client: WebSocket, message_json: str):
        """Send message to a single client with timeout."""
        try:
            # Add timeout to prevent slow clients from blocking
            await asyncio.wait_for(client.send_text(message_json), timeout=0.1)  # 100ms timeout
        except asyncio.TimeoutError:
            # Client is too slow, disconnect them
            raise Exception("Client send timeout")
        except Exception as e:
            # Other send errors
            raise e
    
    async def start_animation(self):
        """Start the animation loop."""
        if self.running:
            return
            
        self.running = True
        self.start_time = time.time()
        self.logger.info(f"Starting animation loop at {self.fps} FPS")
        
        # Create animation task
        self.animation_task = asyncio.create_task(self.animation_loop())
    
    def stop_animation(self):
        """Stop the animation loop."""
        if not self.running:
            return
            
        self.running = False
        self.logger.info("Stopping animation loop")
        
        if hasattr(self, 'animation_task'):
            self.animation_task.cancel()
    
    async def animation_loop(self):
        """Main animation loop that generates and broadcasts frames."""
        frame_count = 0
        perf_log_interval = 60  # Log performance every 60 frames
        target_frame_time = self.start_time  # Track when next frame should be sent
        
        try:
            while self.running:
                loop_start = time.time()
                
                # Always use current real time - never try to "catch up"
                current_time = loop_start - self.start_time
                
                # Generate frame
                gen_start = time.time()
                framebuffer = self.generate_frame(current_time)
                gen_time = time.time() - gen_start
                
                # Broadcast to clients
                broadcast_start = time.time()
                await self.broadcast_frame(framebuffer)
                broadcast_time = time.time() - broadcast_start
                
                # Calculate timing for next frame
                total_elapsed = time.time() - loop_start
                now = time.time()
                
                # Calculate when next frame should start
                next_frame_time = loop_start + self.frame_interval
                sleep_time = max(0, next_frame_time - now)
                
                # If we're running behind, don't sleep at all - proceed immediately
                if sleep_time == 0:
                    # We're behind schedule, so continue immediately for next frame
                    pass
                
                # Performance logging
                frame_count += 1
                if frame_count % perf_log_interval == 0:
                    actual_fps = 1.0 / (total_elapsed + sleep_time) if (total_elapsed + sleep_time) > 0 else 0
                    self.logger.info(f"Performance: gen={gen_time:.3f}s, broadcast={broadcast_time:.3f}s, "
                                   f"total={total_elapsed:.3f}s, target={self.frame_interval:.3f}s, "
                                   f"sleep={sleep_time:.3f}s, actual_fps={actual_fps:.1f}")
                
                if total_elapsed > self.frame_interval * 1.2:  # Warn if > 20% over budget
                    self.logger.warning(f"Frame took {total_elapsed:.3f}s, target was {self.frame_interval:.3f}s, "
                                      f"proceeding immediately")
                
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                # If sleep_time is 0, we proceed immediately without sleeping
        
        except asyncio.CancelledError:
            self.logger.info("Animation loop cancelled")
        except Exception as e:
            self.logger.error(f"Animation loop error: {e}")
    
    async def handle_client_message(self, websocket: WebSocket, data: dict):
        """Handle messages from clients."""
        message_type = data.get("type")
        
        if message_type == "ping":
            # Respond to ping with pong
            response = {"type": "pong", "timestamp": time.time()}
            await websocket.send_text(json.dumps(response))
        elif message_type == "get_pattern_info":
            # Send pattern information
            pattern_info = self.pattern.info()
            response = {"type": "pattern_info", "data": pattern_info}
            await websocket.send_text(json.dumps(response))
        elif message_type == "get_available_patterns":
            # Send list of all available patterns
            # Use patterns directory relative to project root
            patterns_dir = str(Path(__file__).parent.parent)
            available_patterns = discover_patterns(patterns_dir)
            
            pattern_list = []
            for filename, pattern_class in available_patterns.items():
                try:
                    # Create temporary instance to get info
                    temp_pattern = pattern_class()
                    pattern_list.append({
                        "filename": filename,
                        "name": temp_pattern.name,
                        "description": temp_pattern.description
                    })
                except Exception as e:
                    self.logger.warning(f"Could not get info for pattern {filename}: {e}")
            
            response = {"type": "available_patterns", "data": pattern_list}
            await websocket.send_text(json.dumps(response))
        elif message_type == "change_pattern":
            # Switch to a different pattern
            pattern_name = data.get("pattern_name")
            if pattern_name:
                try:
                    # Load the pattern using the correct patterns directory
                    patterns_dir = str(Path(__file__).parent.parent)
                    available_patterns = discover_patterns(patterns_dir)
                    
                    if pattern_name not in available_patterns:
                        raise ValueError(f"Pattern '{pattern_name}' not found")
                    
                    new_pattern = available_patterns[pattern_name]()
                    self.pattern = new_pattern
                    
                    # Send confirmation to all connected clients
                    pattern_info = self.pattern.info()
                    response = {"type": "pattern_changed", "data": pattern_info}
                    
                    # Broadcast to all clients
                    for client in self.connected_clients.copy():
                        try:
                            await client.send_text(json.dumps(response))
                        except Exception:
                            # Remove disconnected clients
                            self.connected_clients.discard(client)
                    
                    self.logger.info(f"Switched to pattern: {self.pattern.name}")
                except Exception as e:
                    # Send error response to requesting client only
                    response = {"type": "error", "message": f"Failed to change pattern: {e}"}
                    await websocket.send_text(json.dumps(response))
                    self.logger.error(f"Pattern change failed: {e}")
        else:
            self.logger.warning(f"Unknown message type from client: {message_type}")


# Global server instance
server_instance: Optional[PatternAnimationServer] = None

# Create FastAPI app
app = FastAPI(title="Luminary Pattern Animation Server")

# Serve static files from webserver directory
static_path = Path(__file__).parent
app.mount("/static", StaticFiles(directory=static_path), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_client():
    """Serve the client HTML page."""
    client_html_path = static_path / "client.html"
    if client_html_path.exists():
        return client_html_path.read_text()
    else:
        return """
        <html>
        <head><title>Luminary Pattern Viewer</title></head>
        <body>
        <h1>Luminary Pattern Viewer</h1>
        <p>Client HTML not found. Please create client.html in the webserver directory.</p>
        </body>
        </html>
        """


@app.get("/pattern-info")
async def get_pattern_info():
    """Get information about the current pattern."""
    if server_instance and server_instance.pattern:
        return server_instance.pattern.info()
    return {"error": "No pattern loaded"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for pattern streaming."""
    if server_instance is None:
        await websocket.close(code=1000, reason="Server not initialized")
        return
    
    await server_instance.register_client(websocket)
    
    try:
        while True:
            # Listen for client messages
            message_text = await websocket.receive_text()
            try:
                data = json.loads(message_text)
                await server_instance.handle_client_message(websocket, data)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON"
                }))
    
    except WebSocketDisconnect:
        server_instance.unregister_client(websocket)


def create_server(net: Net, pattern, fps: float = 30.0) -> PatternAnimationServer:
    """Create and configure the pattern animation server."""
    global server_instance
    server_instance = PatternAnimationServer(net, pattern, fps)
    return server_instance


def main():
    """Main entry point for the pattern animation server."""
    parser = argparse.ArgumentParser(description="Luminary Pattern Animation Server")
    parser.add_argument("config", help="Path to net configuration file")
    parser.add_argument("pattern_name", nargs="?", help="Pattern name (optional, will prompt if omitted)")
    parser.add_argument("--port", type=int, default=8080, help="Server port (default: 8080)")
    parser.add_argument("--fps", type=float, default=30.0, help="Animation frame rate (default: 30.0)")
    parser.add_argument("--host", default="localhost", help="Server host (default: localhost)")
    
    args = parser.parse_args()
    
    try:
        # Load configuration
        config = JSONLoader.load_config(args.config)
        net = Net(config)
        
        # Load or select pattern from the patterns directory
        if args.pattern_name:
            # Use the patterns directory relative to this file
            patterns_dir = str(Path(__file__).parent.parent)
            available_patterns = discover_patterns(patterns_dir)
            
            if args.pattern_name not in available_patterns:
                available = list(available_patterns.keys())
                print(f"Error: Pattern '{args.pattern_name}' not found. Available patterns: {available}")
                return 1
                
            pattern = available_patterns[args.pattern_name]()
        else:
            pattern = get_pattern_or_select(None)  # Interactive selection
        
        # Create server instance
        server = create_server(net, pattern, fps=args.fps)
        
        print(f"Starting Luminary Pattern Animation Server")
        print(f"Configuration: {args.config}")
        print(f"Pattern: {pattern.name}")
        print(f"Server: http://{args.host}:{args.port}")
        print(f"WebSocket: ws://{args.host}:{args.port}/ws")
        print(f"Press Ctrl+C to stop")
        
        # Determine bind host - use 0.0.0.0 for external access, localhost for local
        bind_host = "0.0.0.0" if args.host not in ["localhost", "127.0.0.1"] else args.host
        
        # Run server
        uvicorn.run(app, host=bind_host, port=args.port, log_level="info")
        
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())