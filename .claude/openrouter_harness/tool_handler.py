from __future__ import annotations
import json
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree
import xml.dom.minidom

from .exceptions import NonRetryableError

class ToolHandler:
    def __init__(self, allowed_tools: List[str], cwd: str):
        self.allowed_tools = allowed_tools
        self.cwd = cwd
        self.tool_regex = re.compile(
            r"<([a-zA-Z_]+)[^>]*>(.*?)</\\1>", 
            re.DOTALL
        )

    def extract_tool_calls(self, content: str) -> List[Dict[str, Any]]:
        tool_matches = self.tool_regex.findall(content)
        if not tool_matches:
            return []

        calls = []
        for tool_name, tool_content in tool_matches:
            if tool_name not in self.allowed_tools:
                continue
            
            try:
                params = self._parse_tool_xml(tool_content)
            except NonRetryableError:
                continue
                
            calls.append({
                "tool": tool_name,
                "parameters": params
            })
            
        return calls

    def _parse_tool_xml(self, xml_content: str) -> Dict[str, str]:
        try:
            root = ElementTree.fromstring(f"<root>{xml_content}</root>")
            params = {}
            for child in root:
                params[child.tag] = child.text.strip() if child.text else ""
            return params
        except ElementTree.ParseError as e:
            raise NonRetryableError(f"Invalid tool XML: {e}")

    def execute_tool(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        tool_name = tool_call["tool"]
        params = tool_call["parameters"]
        
        try:
            if tool_name == "execute_command":
                return self._execute_command(
                    params.get("command", ""),
                    params.get("requires_approval", "false").lower() == "true"
                )
            elif tool_name == "write_to_file":
                return self._write_to_file(
                    params["path"],
                    params["content"]
                )
            elif tool_name == "read_file":
                return self._read_file(params["path"])
            else:
                raise NonRetryableError(f"Unsupported tool: {tool_name}")
        except KeyError as e:
            raise NonRetryableError(f"Missing parameter: {e}")

    def _execute_command(self, command: str, requires_approval: bool) -> Dict[str, Any]:
        if requires_approval:
            raise NonRetryableError("Tool execution requires user approval")
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=30
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "return_code": result.returncode
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _write_to_file(self, path: str, content: str) -> Dict[str, Any]:
        try:
            full_path = self._safe_path(path)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            return {"success": True, "path": full_path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _read_file(self, path: str) -> Dict[str, Any]:
        try:
            full_path = self._safe_path(path)
            with open(full_path, "r", encoding="utf-8") as f:
                return {"success": True, "content": f.read()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _safe_path(self, path: str) -> str:
        abs_path = os.path.abspath(os.path.join(self.cwd, path))
        if not abs_path.startswith(self.cwd):
            raise NonRetryableError(f"Path traversal attempt detected: {path}")
        return abs_path

    @staticmethod
    def format_result(tool_result: Dict[str, Any]) -> str:
        return json.dumps(tool_result, indent=2)