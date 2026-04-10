"""Resizable frameless window mixin for tkinter.

Adds edge/corner drag-to-resize functionality to windows
that use overrideredirect(True) (no native title bar).
Only supports right/bottom/corner to avoid title bar conflicts.
"""

# Minimum window size
MIN_WIDTH = 300
MIN_HEIGHT = 200

# Resize handle thickness in pixels
HANDLE_SIZE = 10

# Edge detection flags
EDGE_NONE = 0
EDGE_RIGHT = 1
EDGE_BOTTOM = 2


class ResizableMixin:
    """Mixin that adds edge-drag resize to a frameless tkinter window.

    Call self._setup_resize() after the window and all children are created.
    """

    def _setup_resize(self) -> None:
        """Bind resize events. Call after window creation."""
        self._resize_edge: int = EDGE_NONE
        self._resize_start_x: int = 0
        self._resize_start_y: int = 0
        self._resize_start_w: int = 0
        self._resize_start_h: int = 0

        win = self._resize_win()

        # Bind on the window itself
        win.bind("<Motion>", self._on_resize_motion, add="+")
        win.bind("<ButtonPress-1>", self._on_resize_press, add="+")
        win.bind("<B1-Motion>", self._on_resize_drag, add="+")
        win.bind("<ButtonRelease-1>", self._on_resize_release, add="+")

        # Also bind on all descendant widgets so events aren't swallowed
        self._bind_descendants(win)

    def _bind_descendants(self, widget) -> None:
        """Recursively bind resize events to all child widgets."""
        for child in widget.winfo_children():
            child.bind("<Motion>", self._on_resize_motion, add="+")
            child.bind("<ButtonPress-1>", self._on_resize_press, add="+")
            child.bind("<B1-Motion>", self._on_resize_drag, add="+")
            child.bind("<ButtonRelease-1>", self._on_resize_release, add="+")
            self._bind_descendants(child)

    def _resize_win(self):
        """Return the tkinter window object."""
        return getattr(self, "_win", None) or getattr(self, "_root", None)

    def _to_win_coords(self, event) -> tuple[int, int]:
        """Convert event coordinates to window-relative coordinates."""
        win = self._resize_win()
        return event.x_root - win.winfo_rootx(), event.y_root - win.winfo_rooty()

    def _detect_edge(self, wx: int, wy: int) -> int:
        """Detect which edge(s) the cursor is near. Only right/bottom."""
        win = self._resize_win()
        w = win.winfo_width()
        h = win.winfo_height()
        edge = EDGE_NONE
        if wx > w - HANDLE_SIZE:
            edge |= EDGE_RIGHT
        if wy > h - HANDLE_SIZE:
            edge |= EDGE_BOTTOM
        return edge

    def _edge_cursor(self, edge: int) -> str:
        """Return the appropriate resize cursor."""
        if edge == EDGE_RIGHT | EDGE_BOTTOM:
            return "bottom_right_corner"
        if edge == EDGE_RIGHT:
            return "sb_h_double_arrow"
        if edge == EDGE_BOTTOM:
            return "sb_v_double_arrow"
        return ""

    def _on_resize_motion(self, event) -> None:
        """Update cursor when hovering near edges."""
        if self._resize_edge != EDGE_NONE:
            return
        wx, wy = self._to_win_coords(event)
        edge = self._detect_edge(wx, wy)
        cursor = self._edge_cursor(edge)
        try:
            self._resize_win().configure(cursor=(cursor or "arrow"))
        except Exception:
            pass

    def _on_resize_press(self, event) -> None:
        """Start resize if pressing near an edge."""
        wx, wy = self._to_win_coords(event)
        edge = self._detect_edge(wx, wy)
        if edge != EDGE_NONE:
            self._resize_edge = edge
            self._resize_start_x = event.x_root
            self._resize_start_y = event.y_root
            win = self._resize_win()
            self._resize_start_w = win.winfo_width()
            self._resize_start_h = win.winfo_height()

    def _on_resize_drag(self, event) -> None:
        """Perform resize while dragging."""
        if self._resize_edge == EDGE_NONE:
            return

        win = self._resize_win()
        dx = event.x_root - self._resize_start_x
        dy = event.y_root - self._resize_start_y
        x = win.winfo_x()
        y = win.winfo_y()
        w = self._resize_start_w
        h = self._resize_start_h

        if self._resize_edge & EDGE_RIGHT:
            w = max(MIN_WIDTH, w + dx)
        if self._resize_edge & EDGE_BOTTOM:
            h = max(MIN_HEIGHT, h + dy)

        win.geometry(f"{w}x{h}+{x}+{y}")

    def _on_resize_release(self, event) -> None:
        """Stop resizing."""
        self._resize_edge = EDGE_NONE
