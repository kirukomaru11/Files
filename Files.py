try:
    from Utils import *
except ModuleNotFoundError:
    try:
        from .Utils import *
    except ModuleNotFoundError:
        print("No Utils")
        exit()

import zipfile
import tarfile
from os import stat, fstat
from shutil import disk_usage

class Window(Window):
    __gtype_name__ = "Window"

    prev_button = GObject.Property(type=Gtk.Button)
    next_button = GObject.Property(type=Gtk.Button)
    operations = GObject.Property(type=Gtk.Widget)
    search = GObject.Property(type=Gtk.Widget)
    multi = GObject.Property(type=Adw.MultiLayoutView)
    wide = GObject.Property(type=Adw.ToolbarView)
    narrow = GObject.Property(type=Adw.ToolbarView)
    wide_header = GObject.Property(type=Adw.HeaderBar)
    narrow_header = GObject.Property(type=Adw.HeaderBar)
    context_tab = GObject.Property(type=Adw.TabPage)
    context = GObject.Property(type=Gtk.Widget)
    entry_prompt = GObject.Property(type=EntryPrompt)
    prompt = GObject.Property(type=Prompt)
    view = GObject.Property(type=Adw.TabView)
    standalone = GObject.Property(type=bool, default=False)
    multiple = GObject.Property(type=bool, default=True)
    find = GObject.Property(type=Gtk.SearchEntry)
    drop_target_gtypes = (Gdk.Texture, Gdk.FileList, Gio.File,)

    def __init__(self, standalone=False, multiple=True, tabs=None, **kwargs):
        tabs = tabs or []
        self.__class__.data_init()
        super().__init__(**kwargs)
        self.connect("close-request", self.__class__.handle_close)
        if not APP_CSS in App.default.css:
            App.default.css += APP_CSS
        self.add_css_class("files-window")
        self.connect("notify::focus-widget", self.__class__.handle_focus)
        self.standalone = standalone
        self.multiple = multiple
        if self.standalone: self.add_css_class("standalone")
        self.operations = Operations()
        self.prompt = Prompt(callback=self.__class__.handle_prompt, appearance=Adw.ResponseAppearance.DESTRUCTIVE)
        self.prompt.set_default_response("confirm")
        self.entry_prompt = EntryPrompt(callback=self.__class__.handle_entry_prompt, appearance=Adw.ResponseAppearance.DESTRUCTIVE)
        self.entry_prompt.w = self.prompt.w = self
        self.entry_prompt.set_default_response("confirm")
        self.search = Search()
        self.wide, self.narrow = [Adw.ToolbarView(content=Adw.LayoutSlot.new("content")) for _ in range(2)]
        self.next_button = Button(sensitive=False, icon_name="go-next", tooltip_text="Next", callback=Tab.nav_history)
        self.prev_button = Button(sensitive=False, icon_name="go-previous", tooltip_text="Back", callback=Tab.nav_history)
        default_popover = Gtk.PopoverMenu()
        icon_size = Gtk.Box(css_name="icon-size")
        icon_size.append(Gtk.Label(label="Icon Size", xalign=0))
        box = Gtk.Box(hexpand=True, halign=Gtk.Align.END)
        for i in (Button(callback=self.__class__.button_action, icon_name="zoom-out", tooltip_text="Smaller"), Button(callback=self.__class__.button_action, icon_name="zoom-in", tooltip_text="Larger")):
            i.add_css_class("flat")
            box.append(i)
        icon_size.append(box)
        m = {"New Window": "win.new-window", "Open Trash": "win.context::Open Trash", "Reopen Closed Tab": "win.reopen-tab", "!": Menu({"Icon Size": "custom::size", "Show Names": "show-names", "Thumbnails": "thumbnails", **dict(("Sort by " + it, f"sort::{it}") for it in ("Alphabetical", "Modified", "Content Type", "Size"))})}
        if self.standalone:
            del m["New Window"]
        menu = Menu(m)
        if not self.standalone:
            menu = Menu({"!a": menu, "!b": App.default.default_menu})
        default_popover.set_menu_model(menu)
        default_popover.add_child(icon_size, "size")
        self.menu = Button(t=Gtk.MenuButton, popover=default_popover, tooltip_text="Menu", icon_name="open-menu")
        self.multi = Adw.MultiLayoutView()
        self.view = Adw.TabView()
        overlay = Gtk.Overlay(child=self.view)
        self.find = Gtk.SearchEntry(placeholder_text="Find")
        self.find.connect("activate", self.__class__.do_find)
        self.find.connect("stop-search", self.__class__.stop_find)
        overlay.add_overlay(Gtk.SearchBar(css_name="find", halign=Gtk.Align.CENTER, vexpand=True, child=self.find))
        self.multi.bind_property("layout-name", self.find.get_ancestor(Gtk.SearchBar), "valign", DEFAULT_BIND, self.__class__.multi_bar_bind)
        search_button = Button(t=Gtk.ToggleButton, icon_name="edit-find", tooltip_text="Search")
        self.find.get_ancestor(Gtk.SearchBar).bind_property("search-mode-enabled", search_button, "active", SYNC_BIND)
        for i, w in (("search-button", search_button), ("content", overlay), ("operations", self.operations), ("search", self.search), ("prev", self.prev_button), ("next", self.next_button), ("menu", self.menu),): self.multi.set_child(i, w)
        self.wide_header = Adw.HeaderBar(title_widget=Adw.LayoutSlot.new("search"), show_end_title_buttons=not self.standalone)
        self.narrow_header = Adw.HeaderBar(show_title=False, show_end_title_buttons=False)
        self.wide.add_top_bar(self.wide_header)
        for i in (Adw.LayoutSlot.new("search"), self.narrow_header): self.narrow.add_bottom_bar(i)
        if not self.standalone:
            for i in ("Default Width", "Default Height", "Maximized"): Gio.Application.get_default().lookup_action(i.lower().replace(" ", "-")).bind_property("state", self, i.lower().replace(" ", "-"), SYNC_BIND, unpack_bind, variant_bind)
        for i, n in ((self.wide, "wide"), (self.narrow, "narrow")):
            if not self.standalone: ToolbarFullscreen(i)
            self.multi.add_layout(Adw.Layout(content=i, name=n))
        if not self.standalone: Gio.Application.get_default().lookup_action("fullscreen").connect("notify::state", self.change_fullscreen)
        for i in (self.wide_header, self.narrow_header):
            i.pack_start(Adw.LayoutSlot.new("prev"))
            i.pack_start(Adw.LayoutSlot.new("next"))
            i.pack_end(Adw.LayoutSlot.new("menu"))
            i.pack_end(Adw.LayoutSlot.new("search-button"))
            i.pack_end(Adw.LayoutSlot.new("operations"))
        self.wide_header.pack_start(Button(icon_name="tab-new", tooltip_text="New Tab", callback=Tab.create))
        for i in self.__class__.data.read(table="Tabs", return_dict=True, force_tuple=True): Tab.create(path=i["Path"])
        for i in tabs: Tab.create(path=i)
        if not self.view.get_selected_page(): Tab.create(view=self.view)
        self.wide.add_top_bar(Adw.TabBar(view=self.view))
        overview = Adw.TabOverview(child=self.multi, enable_new_tab=True, view=self.view, secondary_menu=default_popover.get_menu_model())
        overview.connect("create-tab", Tab.overview_create)
        tb = Adw.TabButton(view=self.view)
        tb.connect("clicked", self.__class__.tab_button_clicked)
        self.narrow_header.pack_start(tb)
        self.view.connect("notify::selected-page", Tab.changed)
        self.view.connect("notify::n-pages", Tab.idle_save_all)
        self.view.connect("page-reordered", Tab.idle_save_all)
        self.view.connect("create-window", self.__class__.create)
        self.view.connect("close-page", Tab.operation)
        b = Adw.Breakpoint.new(Adw.BreakpointCondition.new_length(Adw.BreakpointConditionLengthType.MAX_WIDTH, 700, Adw.LengthUnit.PX))
        for i in ("apply", "unapply"): b.connect(i, self.update_css_size)
        b.add_setter(self.multi, "layout-name", "narrow")
        self.add_breakpoint(b)
        self.set_content(overview)
        for n, c in (("context", Context.activate),
                    ("new-window", Window.create),
                    ("reopen-tab", Tab.reopen),
                    ("toggle-find", self.__class__.toggle_find)):
            self.add_action(Gio.SimpleAction.new(n, get_variant("str").get_type() if n == "context" else None))
            self.lookup_action(n).window = self
            self.lookup_action(n).connect("activate", c)
        self.lookup_action("reopen-tab").set_enabled(False)
        if self.standalone: self.set_default_size(702, 600)
        else:
            self.change_fullscreen()
            self.present()

    def handle_close(self):
        for i in self.view.get_pages():
            if hasattr(i.get_child().get_child(), "cancellable"): i.get_child().get_child().cancellable.cancel()

    @staticmethod
    def button_action(b): Context.action(action="Icon " + b.get_tooltip_text())

    @staticmethod
    def toggle_find(a, p):
        s = a.window.find.get_ancestor(Gtk.SearchBar)
        s.set_search_mode(not s.get_search_mode())
        if s.get_search_mode() and Tab.current:
            a.window.find.set_text(Tab.current.get_child().search if Tab.current.get_child() else "")
            a.window.find.set_position(-1)

    @staticmethod
    def do_find(s):
        if not (Tab.current and Tab.current.get_child()): return
        view = Tab.current.get_child().search = s.get_text()

    @staticmethod
    def data_uninit():
        if hasattr(Window, "data"):
            Window.data.close()
            del Window.data

    @staticmethod
    def data_init():
        if hasattr(Window, "data"):
            try: Window.data.execute("SELECT 1")
            except Exception as e: Window.data_uninit()
        if not hasattr(Window, "data"):
            if App.default.get_application_id().endswith("Files"):
                Window.data = App.default.data
            else:
                d = Path(MAIN_HOME, ".var", "app", INFO["ID"], "data")
                flatpak_data = Path(d, "data")
                if exists(flatpak_data):
                    a = flatpak_data
                    global TRASH
                    TRASH = Path(d, "Trash")
                else:
                    a = Path(DATA, "Files", "data")
                Window.data = Data(a, DATA_INIT)
        for k, v in {"Sort": "Alphabetical", "Icon Size": 128, "Show Names": True, "Thumbnails": False, "Default Width": 360, "Default Height": 600, "Maximized": False, "Fullscreen": False }.items():
            name = k.lower().replace(" ", "-")
            if not App.default.lookup_action(name):
                Window.data.persist_action(App.default, name, (k, v), "Settings", "Value", "Key = ?", (k,))
                if name == "sort": App.default.lookup_action(name).connect("notify::state", sort_reload)

    @staticmethod
    def stop_find(s): s.get_root().activate_action("find-bar")

    @staticmethod
    def multi_bar_bind(b, v): return Gtk.Align.END if v == "narrow" else Gtk.Align.START

    @staticmethod
    def handle_focus(self, p=None):
        if self.get_focus():
            if self.get_focus() == self.search.text: return
            elif self.search.text.get_mapped(): self.search.set_preview()

    @staticmethod
    def on_scroll(e, x, y):
        if Gdk.ModifierType.CONTROL_MASK in e.get_current_event_state():
            a = Gio.Application.get_default().lookup_action("icon-size")
            a.set_state(get_variant(int(a.get_state().unpack() + (-y * 4))))
            return True

    @staticmethod
    def handle_prompt(d):
        infos = d.infos
        if d.get_heading().startswith("Delete "):
            for i in infos: Operation.delete(i.path)

    @staticmethod
    def handle_entry_prompt(d):
        if not d.get_extra_child().get_text(): return
        tab = d.w.view.get_selected_page().get_child()
        widget = d.infos[0]
        f = Path(tab.path if d.get_heading().startswith("New ") else get_parent(widget.path), d.get_extra_child().get_text())
        if d.get_heading().startswith("Rename "): Operation.move(widget.path, f)
        if d.get_heading().startswith("New "): Operation.new_link(f) if d.get_heading().endswith("Link") else Operation.new_file(f) if d.get_heading().endswith("File") else Operation.new_folder(f)

    @staticmethod
    def on_key_pressed(e, v, kc, s):
        self = e.get_widget()
        if not self: return
        if self.get_visible_dialog(): return
        t = self.view.get_selected_page().get_child()
        view = t.get_child() if isinstance(t.get_child(), View) else False
        if v == Gdk.KEY_Escape:
            if self.search.autocomplete.get_mapped(): return
            if self.search.text.get_mapped():
                self.search.toggle()
                return True
            if "toolbar-fullscreen" in self.get_css_classes() and self.search.get_ancestor(Gtk.Revealer).get_reveal_child():
                self.search.get_ancestor(Gtk.Revealer).set_reveal_child(False)
                return True
            if self.find.get_mapped():
                self.stop_find(self.find)
                return True
            if self.context and self.context.get_mapped():
                self.context.popdown()
                return True
            if view and view.get_selected():
                view.selection.unselect_all()
                return True
            if self.standalone:
                self.close()
                return True
        if Gdk.ModifierType.CONTROL_MASK in s and v == Gdk.KEY_l: Gio.Application.get_default().lookup_action("show-names").activate()
        if not self.standalone:
            f = Gio.Application.get_default().lookup_action("fullscreen")
            if f and v == Gdk.KEY_F11:
                f.activate()
                return True
        if Gdk.ModifierType.CONTROL_MASK in s and Gdk.ModifierType.SHIFT_MASK in s and v in (Gdk.KEY_t, Gdk.KEY_T):
            self.lookup_action("reopen-tab").activate()
            return True
        if Gdk.ModifierType.CONTROL_MASK in s and v == Gdk.KEY_n:
            self.lookup_action("new-window").activate()
            return True
        if Gdk.ModifierType.CONTROL_MASK in s and v == Gdk.KEY_t: return bool(Tab.create())
        if Gdk.ModifierType.CONTROL_MASK in s and v == Gdk.KEY_f: self.lookup_action("toggle-find").activate()
        if Gdk.ModifierType.CONTROL_MASK in s and v == Gdk.KEY_o: self.get_content().set_open(not self.get_content().get_open())
        if Gdk.ModifierType.CONTROL_MASK in s and v == Gdk.KEY_minus: Context.action(action="Icon Smaller")
        if Gdk.ModifierType.CONTROL_MASK in s and v == Gdk.KEY_equal: Context.action(action="Icon Larger")
        if Gdk.ModifierType.CONTROL_MASK in s and v == Gdk.KEY_s:
            self.search.get_ancestor(Gtk.Revealer).set_reveal_child(True)
            self.search.set_text("")
            self.search.grab_focus()
            return True
        if Gdk.ModifierType.CONTROL_MASK in s and v == Gdk.KEY_w:
            Tab.operation(None, t)
            return True
        if t and (v == Gdk.KEY_F5 or Gdk.ModifierType.CONTROL_MASK in s and Gdk.ModifierType.CONTROL_MASK in s and v == Gdk.KEY_r):
            Context.action(widget=t.get_child(), action="Reload")
            return True
        if isinstance(self.get_focus(), Gtk.Editable) or isinstance(self.get_focus(), Gtk.TextView): return
        if not self.get_visible_dialog():
            if Gdk.ModifierType.CONTROL_MASK in s and v == Gdk.KEY_c: Context.action(widget=t.get_child(), action="Copy")
            if Gdk.ModifierType.CONTROL_MASK in s and v == Gdk.KEY_x: Context.action(widget=t.get_child(), action="Cut")
            if Gdk.ModifierType.CONTROL_MASK in s and v == Gdk.KEY_v: Context.action(widget=t.get_child(), action="Paste")
        if view:
            if t and Gdk.ModifierType.SHIFT_MASK in s and v == Gdk.KEY_Return:
                self.key_to_click(v, mask=s)
                return True
            if v == Gdk.KEY_space:
                self.key_to_click(v, mask=s)
                return True
            if v == Gdk.KEY_Menu:
                self.key_to_click(v, mask=s)
                return True
            if v == Gdk.KEY_Delete: Context.action(widget=t.get_child(), action="Delete" if Gdk.ModifierType.SHIFT_MASK in s else "Trash")
            if Gdk.ModifierType.SHIFT_MASK in s and v == Gdk.KEY_r or v == Gdk.KEY_R: Context.action(widget=t.get_child(), action="Rename")
            if Gdk.ModifierType.SHIFT_MASK in s and v == Gdk.KEY_s or v == Gdk.KEY_S: Context.action(widget=t.get_child(), action="Properties")
            if Gdk.ModifierType.CONTROL_MASK in s and v in (Gdk.KEY_a, Gdk.KEY_A):
                if len([i for i in t.get_child().get_selected()]) == t.get_child().selection.get_n_items(): t.get_child().selection.unselect_all()
                else: t.get_child().selection.select_all()
        if not Gdk.ModifierType.CONTROL_MASK in s and not isinstance(self.get_focus(), Gtk.Text) and Gdk.keyval_to_unicode(v) != 0 and len(Gdk.keyval_name(v)) == 1 :
            if self.find.get_mapped(): self.find.grab_focus()
            else:
                if self.search.text.get_mapped(): self.search.grab_focus()
                else: self.search.set_editing()

    @staticmethod
    def tab_button_clicked(b):
        if not b.get_view().get_n_pages(): Tab.create(view=b.get_view())
        b.get_view().get_ancestor(Adw.TabOverview).set_open(not b.get_view().get_ancestor(Adw.TabOverview).get_open())

    @staticmethod
    def create(*_): return Window().view

    @staticmethod
    def find_reveal_bind(b, v): return Gtk.RevealerTransitionType.SLIDE_DOWN if v == Gtk.Align.START else Gtk.RevealerTransitionType.SLIDE_UP

    @staticmethod
    def on_click(*args):
        self, e, n, x, y, signal, b, state = Window.click_to_args(*args)
        if self.context and self.context.get_mapped(): return self.context.popdown()
        if isinstance(e, Gtk.GestureLongPress): return self.on_click(self, x, y, "released", 3, state)
        if signal != "released": return
        if b == 8: return Task.invoke(self.prev_button.emit, "clicked")
        elif b == 9: return Task.invoke(self.next_button.emit, "clicked")
        if self.search.autocomplete.get_mapped(): return self.search.autocomplete.popdown()
        w = self.pick(x, y, Gtk.PickFlags.DEFAULT)
        if not w: return
        search = w.get_ancestor(Search)
        if search:
            if b == 1:
                if any(isinstance(w, i) for i in (Gtk.Box, Adw.ViewStack, Gtk.Viewport, Adw.Clamp)):
                    w.get_ancestor(Search).toggle()
                    return
            button = w if isinstance(w, Gtk.Button) else w.get_ancestor(Gtk.Button)
            if b == 2 and button and search.get_child().get_visible_child_name() == "Preview":
                Tab(path=Search.get_button_path(button))
                return
        if b == 3:
            item = w.get_ancestor(GridItem)
            if item:
                item = item.info
            else:
                item = None
            view = w.get_ancestor(View)
            if not view: return
            if item: view.select(item, unselect=not view.is_selected(item))
            all_items = [i for i in view.get_items()]
            items = [i for i in view.get_selected()]
            menu = Menu()
            me = {"Actions": ["Unselect All" if len(all_items) == len(items) else "Select All"] if isinstance(view.selection, Gtk.MultiSelection) and len(all_items) > 1 else [], "Clipboard": ["Cut", "Copy", "Move to...", "Copy to..."], "Danger": ["Delete" if Gdk.ModifierType.SHIFT_MASK in state or view.info.is_trash or item and item.is_trash else "Trash"], "Rest": ["Properties"]}
            if len(items) == 1: me["Danger"].insert(0, "Rename")
            self.context = self.context or Context()
            if any(i.is_archived for i in items):
                me["Clipboard"] = ["Copy", "Copy to..."]
            if item:
                self.context.widget = w.get_ancestor(GridItem)
                if item.is_dir or item.is_archived or item.is_dir_link:
                    if Gdk.ModifierType.SHIFT_MASK in state: me["Actions"].insert(0, "Open")
                    else: me["Actions"].insert(0, "Open in New Tab")
                    if not view.info.is_archived and any(i.is_copy or i.is_cut for i in Info.files): me["Clipboard"].append("Paste")
                elif not item.is_archived: me["Actions"].insert(0, "Open")
                if item.is_archived:
                    del me["Danger"]
                if not any(i.is_archived for i in items): me["Actions"].append("Compress")
            else:
                if any(i.is_copy or i.is_cut for i in Info.files): me["Clipboard"].append("Paste")
                ex = view.info.exists if view.info else False
                if not ex or view.info.is_mountpoint or view.info.is_trash or view.info.is_archived:
                    me["Clipboard"] = []
                del me["Danger"]
                me["Rest"].insert(0, "Reload")
                if not (not ex or view.info.is_trash or view.info.is_archived): me["Rest"].insert(0, "New")
                self.context.widget = view
                if Gdk.ModifierType.SHIFT_MASK in state and not view.is_archived: me["Actions"].insert(0, "Open")
            for k, v in me.items():
                if not v: continue
                if len(v) == 1: menu.parse({v[0]: f"win.context::{v[0].strip('.')}"})
                elif k in ("Actions", "Danger", "Rest"):
                    mm = Menu()
                    menu.append_section(None, mm)
                    for i in v:
                        if i == "New":
                            mm = Menu()
                            menu.append_section(None, mm)
                            mm.append_submenu(i, Menu(dict((it, f"win.context::New {it}") for it in ("File", "Folder", "Link"))))
                        else: mm.append(i, f"win.context::{i.strip('.')}")
                else: menu.append_submenu(k, Menu(dict((i, f"win.context::{i.strip('.')}") for i in v)))
            self.context.set_menu_model(menu)
            self.show_popover_at_widget(self.context, view, x, y)
        elif b == 2 and w.get_ancestor(GridItem):
            info = w.get_ancestor(GridItem).info
            if info.is_dir or info.is_archive or info.is_dir_link:
                w.get_ancestor(View).select(info, unselect=not Gdk.ModifierType.SHIFT_MASK in state and not Gdk.ModifierType.CONTROL_MASK in state)
                Context.action(widget=w.get_ancestor(GridItem), action="Open in New Tab")
        elif b == 1 and not Gdk.ModifierType.SHIFT_MASK in state and not Gdk.ModifierType.CONTROL_MASK in state and not w.get_ancestor(GridItem) and w.get_ancestor(View): w.get_ancestor(View).selection.unselect_all()

    def update_css_size(self, b):
        if not self.get_current_breakpoint(): self.add_css_class("small")
        else: self.remove_css_class("small")

    @staticmethod
    def on_map(self): Tab.changed(self.view)

    def get_all_items(self, current_view=False, selected=False):
        if current_view and hasattr(self, "view"): return [i for i in self.view.get_selected_page().get_child().get_child().get_items()]
        selecteds = []
        if hasattr(self, "view"):
            for i in self.view.get_pages():
                v = i.get_child().get_child()
                if not isinstance(v, View): continue
                if selected: selecteds.extend([i for i in v.get_selected()])
                else: selecteds.extend([i for i in v.get_items()])
        elif isinstance(self.get_child(), View):
            if selected: selecteds.extend([i for i in self.get_child().get_selected()])
            else: selecteds.extend([i for i in self.get_child().get_items()])
        return selecteds

    def get_all_selected_items(self, current_view=False): return self.get_all_items(current_view=current_view, selected=True)

    @staticmethod
    def on_drag_source_prepare(e, x, y):
        self = e.get_widget().get_root()
        w = self.pick(x, y, Gtk.PickFlags.DEFAULT)
        w = w.get_ancestor(GridItem) if w else None
        e.files = c = None
        if w:
            w.get_ancestor(View).select(w.info, unselect=False)
            e.files = [i for i in w.get_ancestor(View).get_selected()]
            if e.files:
                if Gdk.ModifierType.CONTROL_MASK in e.get_current_event_state() or any(i.is_archived for i in e.files): e.set_actions(Gdk.DragAction.COPY)
                else: e.set_actions(Gdk.DragAction.MOVE)
                c = Gdk.ContentProvider.new_for_value(Gdk.FileList.new_from_list([Gio.File.new_for_path(i.path) for i in e.files]))
        else: e.set_actions(Gdk.DragAction.NONE)
        e.set_content(c)
        return c

    @staticmethod
    def on_drag_source_drag_begin(e, d):
        self = e.get_widget().get_root()
        if e.files:
            box = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE)
            for n, i in enumerate(e.files):
                if n == 8 and not i == e.files[-1]:
                    box.append(Gtk.Label(opacity=0.4, css_classes=("title-2",), label=f"{len(e.files) - 8} +"))
                    break
                im = Gtk.Image(pixel_size=92)
                i.set_image_icon(im)
                box.append(im)
            Gtk.DragIcon.get_for_drag(d).set_child(Adw.Clamp(maximum_size=300, child=box))

    @staticmethod
    def on_drag_source_drag_end(e, d, de):
        e.set_content(None)
        e.set_actions(Gdk.DragAction.NONE)
        e.files = None

    @staticmethod
    def on_drop_target_motion(e, x, y):
        self = e.get_widget().get_root()
        w = getattr(self, "highlight", None)
        if w: w.remove_css_class("highlight")
        h = self.pick(x, y, Gtk.PickFlags.DEFAULT)
        h = (h.get_ancestor(GridItem) or h.get_ancestor(View)) if h else None
        tab = self.view.get_selected_page().get_child()
        if not tab or isinstance(tab.get_child(), View) and (tab.get_child().info.is_archived or tab.get_child().extra_status.get_visible()): return Gdk.DragAction.NONE
        if h and h.info.is_dir:
            self.highlight = h
            h.add_css_class("highlight")
        else:
            self.highlight = None
        return Gdk.DragAction.COPY

    @staticmethod
    def on_drop_target_drop(e, v, x, y):
        self = e.get_widget().get_root()
        w = getattr(self, "highlight", None)
        if not w: return
        tab = w.get_ancestor(Tab)
        file = Gio.File.new_for_path(w.info.path)
        w.remove_css_class("highlight")
        self.highlight = None
        if isinstance(v, Gio.File):
            v = Gdk.FileList.new_from_list([v])
        if isinstance(v, Gdk.FileList):
            action = Operation.move if e.get_current_drop().get_actions() == Gdk.DragAction.MOVE else Operation.copy
            for i in v: action(i.get_path(), unique_name(basename(i), file).get_path())
        if isinstance(v, Gdk.Texture): v.save_to_png(unique_name("image", d=file, end=".png").get_path())
        tab.load(history=True)

class Search(Adw.Bin):
    __gtype_name__ = "Search"

    text = GObject.Property(type=Gtk.Text)
    preview = GObject.Property(type=Gtk.ScrolledWindow)
    autocomplete = GObject.Property(type=Autocomplete)
    completer = Gio.FilenameCompleter()
    completer.set_dirs_only(True)

    def __init__(self):
        super().__init__(child=Adw.ViewStack(vhomogeneous=False, hhomogeneous=False, enable_transitions=True), css_name="search")
        self.text = Gtk.Text(placeholder_text="Search", xalign=0.50, hexpand=True)
        self.preview = Gtk.ScrolledWindow(child=Gtk.Box(valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER, hexpand=True), propagate_natural_width=True, vscrollbar_policy=Gtk.PolicyType.NEVER)
        self.get_child().connect("notify::visible-child-name", self.__class__.apply_class)
        self.get_child().add_named(self.preview, "Preview")
        self.get_child().add_named(Adw.Clamp(orientation=Gtk.Orientation.HORIZONTAL, child=self.text, maximum_size=650, tightening_threshold=650, hexpand=True), "Editing")
        self.autocomplete = Autocomplete(self.text, select=True, bind=self.__class__.bind, text_activate=self.__class__.text_activate, complete=self.__class__.complete)

    @staticmethod
    def bind(f, l):
        l.get_child().bindings = [l.get_property("item").bind_property("string", l.get_child(), "label", DEFAULT_BIND, Search.text_bind)]

    @staticmethod
    def text_bind(b, v): return basename(v)

    @staticmethod
    def text_activate(text, autocomplete, s):
        te = text.get_ancestor(Search).get_text()
        if te.startswith("file://"):
            te = uri_decode(te)
        if Gdk.ModifierType.SHIFT_MASK in s:
            Tab.create(path=te)
            return True
        else:
            t = Tab.current
            if not t: return
            t.path = te
            t.load()
            Tab.idle_save_all()
            return True

    @staticmethod
    def complete(autocomplete, text):
        t = uri_decode(text.get_text()) if text.get_text().startswith("file://") else text.get_text()
        autocomplete.model.replace([i.rstrip("/") for i in Search.completer.get_completions(t)])
        autocomplete.listview.get_model().unselect_all()

    @staticmethod
    def apply_class(v, p):
        for i in v.get_pages():
            if i.get_name() == v.get_visible_child_name(): v.get_parent().add_css_class(i.get_name().lower())
            else: v.get_parent().remove_css_class(i.get_name().lower())

    def set_position(self, p=-1): self.text.set_position(p)

    def set_text(self, t=""):
        box = self.preview.get_child().get_child()
        while box.get_first_child(): box.get_first_child().unparent()
        t = display(t)
        for i in t.strip(SEPARATOR).split(SEPARATOR): box.append(Button(label=i, callback=self.__class__.do_folder))
        if box.get_last_child():
            if box.get_first_child() == box.get_last_child() and not box.get_last_child().get_label(): box.get_last_child().set_label("Computer")
            box.get_last_child().set_sensitive(False)
        self.autocomplete.set_text(t)

    @staticmethod
    def get_button_path(b):
        t = ROOT
        for i in b.get_parent():
            t += SEPARATOR + i.get_label()
            if i == b: break
        s = t.rstrip(SEPARATOR)
        if s.endswith("|") and not exists(s):
            s = s.rsplit("|", 1)[0]
        if s.startswith("//"):
            s = "/" + s.split("//", 1)[-1]
        return s

    @staticmethod
    def do_folder(b):
        b.get_root().view.get_selected_page().get_child().path = Search.get_button_path(b)
        b.get_root().view.get_selected_page().get_child().load()

    def get_text(self):
        t = self.text.get_text()
        if FLATPAK_ID:
            t = Path(ROOT, t)
        return t

    def set_preview(self):
        self.get_child().set_visible_child_name("Preview")
        self.get_ancestor(Gtk.Revealer).set_reveal_child(True)

    def set_editing(self):
        self.get_child().set_visible_child_name("Editing")
        self.get_ancestor(Gtk.Revealer).set_reveal_child(True)
        Task.invoke(self.text.grab_focus)
        Task.invoke(self.text.set_position, -1)

    def toggle(self, *_):
        if not isinstance(self, Search):
            self = self.get_ancestor(Search)
        if self.get_child().get_visible_child_name() == "Preview": self.set_editing()
        else: self.set_preview()

class Tab(Adw.Bin):
    __gtype_name__ = "Tab"
    tab = GObject.Property(type=Adw.TabPage)
    path = GObject.Property(type=str)
    history = GObject.Property(type=object)
    index = GObject.Property(type=int, minimum=0)
    closed = []

    @classproperty
    def current(*_): return Window.current.view.get_selected_page().get_child() if Window.current and Window.current.view.get_selected_page() else None

    def __init__(self, path=False, view=None, prepend=False):
        super().__init__(css_name=self.__gtype_name__.lower())
        view = view or Window.current.view
        current_tab = self.__class__.current
        if path == False:
            path = current_tab.path if current_tab else MAIN_HOME
        if FLATPAK_ID:
            if not path.startswith(ROOT):
                path = Path(ROOT, path)
        if prepend:
            self.tab = view.prepend(self)
        else:
            self.tab = view.add_page(self, current_tab.tab if current_tab else None) if view.get_mapped() else view.append(self)
        self.path = path
        self.bind_property("path", self.tab, "title", DEFAULT_BIND, self.__class__.title_bind)

    @staticmethod
    def create(*_, view=False, path=False, prepend=False): return Tab(view=view if isinstance(view, Adw.TabView) else False, path=path, prepend=prepend)

    @staticmethod
    def overview_create(*_): return Tab.create().tab

    @staticmethod
    def reopen(a, *_):
        if Tab.closed:
            p = Tab.closed.pop(-1)
            while p in Tab.closed: Tab.closed.remove(p)
            Tab.create(view=a.window.view, path=p)
            a.window.lookup_action("reopen-tab").set_enabled(bool(Tab.closed))

    @staticmethod
    def nav_history(b):
        tab = b.get_root().view.get_selected_page().get_child()
        if not b.get_sensitive() or not tab: return
        if "next" in b.get_icon_name():
            if not tab.history or tab.index >= len(tab.history): return tab.sync()
        else:
            if tab.index == 0: return tab.sync()
        tab.index += (1 if "next" in b.get_icon_name() else -1)
        tab.load(history=True)

    @staticmethod
    def title_bind(b=None, v=""): return "Computer" if v in ("", ROOT, SEPARATOR, ROOT + SEPARATOR) else "Home" if v == MAIN_HOME else basename(v) if v else "Untitled"

    def load(self, history=False):
        if isinstance(self.get_child(), View) and self.get_child().spinner.get_visible(): return
        if history:
            self.path = self.history[self.index]
        else:
            if not self.history:
                self.history = []
            if self.index != len(self.history) - 1:
                self.history = self.history[0:self.index + 1]
            if not self.path in self.history: self.history.append(self.path)
            self.index = self.history.index(self.path)
        if self.path != ROOT:
            self.path = self.path.rstrip(GLib.DIR_SEPARATOR_S)
        if isinstance(self.get_child(), View):
            self.get_child().path = self.path
        else: self.set_child(View(multiple=self.get_root().multiple, path=self.path, root=self.get_root()))
        self.sync()

    def sync(self):
        w = self.get_root()
        if not w: return
        w.prev_button.set_sensitive(len(self.history) - 1 >= self.index and self.index != 0)
        w.next_button.set_sensitive(len(self.history) > self.index + 1)
        w.search.set_text(self.path)
        w.search.set_position(-1)
        if self.get_child():
            w.find.set_text(self.get_child().search)
            w.find.set_position(-1)
            if w.find.get_text() and not w.find.get_mapped(): w.toggle_find()

    @staticmethod
    def changed(view, *_):
        self = Tab.current
        if not self or not view.get_mapped(): return
        if self.get_child(): Task.invoke(self.sync)
        else: Task.invoke(self.load)

    @staticmethod
    def idle_save_all(*_): Task.invoke(Tab.get_all, save=True)

    @staticmethod
    def get_all(save=False, window=None):
        tabs = []
        cleared = False
        for w in Gio.Application.get_default().get_windows():
            if not isinstance(w, Window) or not isinstance(getattr(w, "view", None), Adw.TabView) or save and (w.standalone or not w.get_mapped()): continue
            for i in w.view.get_pages():
                if isinstance(i.get_child(), Tab): tabs.append(i.get_child())
        if tabs and save:
            r = tabs[-1].get_root()
            if not r: return
            Window.data_init()
            try: Window.data.table_clear(table="Tabs")
            except: return
            for i in tabs:
                if i.get_root() == r: Window.data.new(table="Tabs", values=(None, i.path, ))
        return tabs

    @staticmethod
    def operation(v=None, t=None):
        if isinstance(t, Adw.TabPage):
            t = t.get_child()
        view = t.get_ancestor(Adw.TabView)
        if not v:
            if hasattr(t.get_child(), "cancellable"): t.get_child().cancellable.cancel()
            view.close_page(t.tab)
        Tab.closed.append(t.path)
        view.get_root().lookup_action("reopen-tab").set_enabled(bool(Tab.closed))

class Info(Gio.FileInfo):
    __gtype_name__ = "Info"
    archive_types = ("application/zip", "application/x-gtar", "application/x-tar", "application/x-xz-compressed-tar", "application/x-compressed-tar")
    attributes = "standard::name,standard::display-name,standard::type,standard::icon,standard::is-symlink,standard::symlink-target,standard::content-type,standard::size,time::modified,metadata::custom-icon,unix::is-mountpoint"
    path = GObject.Property(type=str)

    is_cut = GObject.Property(type=bool, default=False)
    is_copy = GObject.Property(type=bool, default=False)
    is_archived = GObject.Property(type=bool, default=False)

    display_icon = GObject.Property(type=object)

    @GObject.Property(type=GLib.DateTime)
    def modification(self): return self.get_modification_date_time() if self.has_attribute("time::modified") else None

    @modification.setter
    def modification(self, value): self.set_modification_date_time(value)

    @GObject.Property(type=str)
    def content_type(self): return self.get_content_type() if self.has_attribute("standard::content-type") else ("inode/directory" if self.exists and is_dir(self.path) else Gio.content_type_guess(self.path)[0]) if self.path else None

    @content_type.setter
    def content_type(self, value): self.set_content_type(value)

    @GObject.Property(type=int)
    def size(self): return self.get_size() if self.has_attribute("standard::size") else 0

    @size.setter
    def size(self, value): self.set_size(value)

    @GObject.Property(type=bool, default=False)
    def is_symlink(self): return self.get_is_symlink() if self.has_attribute("standard::is-symlink") else False

    @is_symlink.setter
    def is_symlink(self, value): self.set_is_symlink(value)

    @GObject.Property(type=str)
    def symlink_target(self): return self.get_attribute_as_string("standard::symlink-target") if self.has_attribute("standard::symlink-target") else ""

    @symlink_target.setter
    def symlink_target(self, value): self.set_attribute_byte_string("standard::symlink-target", value, Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS)

    @GObject.Property(type=str)
    def custom_icon(self):
        path = display(self.path)
        Window.data_init()
        if path and Window.data.exists(table="Icons", conditions="Path = ?", conds=(path,)): return Window.data.read(table="Icons", column="Icon", conditions="Path = ?", conds=(path,))
        else: return self.get_attribute_as_string("metadata::custom-icon") if self.has_attribute("metadata::custom-icon") else ""

    @custom_icon.setter
    def custom_icon(self, v):
        Window.data_init()
        p = display(self.path)
        Window.data.set_default(table="Icons", conditions="Path = ?", conds=(p,), values=(p, v))
        if v: Window.data.update(table="Icons", conditions="Path = ?", column="Icon", conds=(p,), value=v)
        else: Window.data.delete(table="Icons", conditions="Path = ?", conds=(p,))
        if exists("/usr/lib/gvfsd-metadata"): self.set_attribute_string("metadata::custom-icon", v, Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS)

    @GObject.Property(type=Gio.Icon)
    def icon(self):
        if self.has_attribute("standard::icon"): return self.get_icon()
        if self.content_type: return Gio.content_type_get_icon(self.content_type)

    @icon.setter
    def icon(self, value): self.set_icon(value)

    @GObject.Property(type=Gio.FileType, default=Gio.FileType.UNKNOWN)
    def file_type(self): return self.get_file_type() if self.has_attribute("standard::type") else Gio.FileType.UNKNOWN

    @file_type.setter
    def file_type(self, value): self.set_file_type(value)

    @GObject.Property(type=str)
    def name(self): return self.get_name()

    @name.setter
    def name(self, value):
        self.set_name(value)
        self.path = Path(get_parent(self.path), self.get_name())

    def from_info(self, info):
        info.copy_into(self)
        for i in ("file-type", "icon", "custom-icon", "symlink-target", "is-symlink", "content-type", "modification", "size"): self.notify(i)

    @property
    def exists(self): return self.path and exists(self.path)

    @property
    def is_trash(self):
        s = (self.path or "").rstrip("/")
        return s.startswith(TRASH) or s == TRASH.rstrip("/")

    @property
    def is_archive(self): return (self.content_type or "").startswith(Info.archive_types)

    @property
    def is_dir(self): return (self.content_type or "") == "inode/directory"

    @property
    def is_dir_link(self): return self.is_symlink and is_dir(GLib.canonicalize_filename(self.symlink_target, get_parent(self.path) or "/"))

    @property
    def is_mountpoint(self): return self.get_attribute_boolean("unix::is-mountpoint") if self.has_attribute("unix::is-mountpoint") else False

    @staticmethod
    def get_archive(path, e=False): return path.split("|/", 1)[0] if e or "|/" in path and exists(path.split("|/", 1)[0]) else path if exists(path) else ""

    @staticmethod
    def archive_get(path): return path.split("|/", 1)[-1]

    @staticmethod
    def query_info(path): return Gio.File.new_for_path(path).query_info(Info.attributes, Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS)

    @staticmethod
    def parse_dir(path, cancellable=None, search=""):
        if isinstance(path, str):
            f = Gio.File.new_for_path(path)
        else:
            f = path
        e = [None, cancellable]
        cancellable.event = Event()
        f.enumerate_children_async(Info.attributes, Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, GLib.PRIORITY_DEFAULT, cancellable, Info.do_enumerator, e)
        cancellable.event.wait()
        enumerator = e[0]
        if isinstance(e[0], Exception):
            if search: return Task.invoke(Toast, str(e[0]).split("g-io-error-quark:", 1)[-1])
            else: raise e[0]
        if cancellable and cancellable.is_cancelled(): return
        if not isinstance(enumerator, Gio.FileEnumerator): return cancellable.cancel()
        e[0] = []
        cancellable.event = Event()
        enumerator.next_files_async(10000, GLib.PRIORITY_DEFAULT, cancellable, Info.do_parse, e)
        cancellable.event.wait()
        for n in e[0]:
            if cancellable and cancellable.is_cancelled(): return
            file = enumerator.get_child(n)
            if not (search and not search in n.get_name().lower()):
                info = Info(path=file.get_path(), info=n)
            if search and n.get_file_type() == Gio.FileType.DIRECTORY:
                error = Info.parse_dir(file, cancellable=cancellable, search=search)

    @staticmethod
    def do_enumerator(f, r, e):
        try:
            e[0] = f.enumerate_children_finish(r)
        except Exception as ex:
            e[0] = ex
        e[1].event.set()

    @staticmethod
    def do_parse(enumerator, b, e):
        if e[1].is_cancelled(): return
        try:
            files = enumerator.next_files_finish(b)
        except Exception as ex:
            print(ex)
            files = []
        e[0].extend(files)
        if len(files) == 10000: enumerator.next_files_async(10000, GLib.PRIORITY_DEFAULT, e[1], Info.do_parse, e)
        else: e[1].event.set()

    def __new__(cls, info=False, do_info=True, **kwargs):
        kwargs["path"] = kwargs["path"].rstrip("/")
        f = Info.files[kwargs["path"]]
        if f:
            if info and not f.is_archived: f.from_info(info)
            else:
                for k, v in kwargs.items():
                    if not getattr(f, k, False) == v: setattr(f, k, v)
            return f
        f = super().__new__(cls)
        f.__init__(**kwargs)
        if do_info and not f.is_archived and f.path and not info:
            try:
                info = cls.query_info(f.path)
            except: pass
        if isinstance(info, Gio.FileInfo): f.from_info(info)
        for i in ("custom-icon", "content-type", "icon"): f.connect(f"notify::{i}", cls.do_icon)
        Info.files.append(f)
        f.do_icon()
        return f

    def get_name(self):
        if self.is_archived: return basename(self.path)
        else: return Gio.FileInfo.get_name(self)

    def modified_expression(self): return self.modification.to_unix()

    def get_sorter():
        s = App.default.lookup_action("sort").get_state().unpack()
        sor = Info.alphabetical_sort
        if s == "Content Type":
            sor = Info.content_type_sort
        if s == "Modified":
            sor = Info.modified_sort
        if s == "Size":
            sor = Info.size_sort
        sorter = Gtk.MultiSorter()
        sorter.append(Info.folder_sort)
        sorter.append(sor)
        return sorter
    folder_sort = Gtk.CustomSorter()
    def do_folder_sort(a, b, d):
        a_dir = a.is_dir
        if a_dir != b.is_dir: return -1 if a_dir else 1
        return 0
    folder_sort.set_sort_func(do_folder_sort)

    def do_icon(self, *_):
        try:
            custom = self.custom_icon
        except:
            custom = False
        if custom and isinstance(custom, str):
            if Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).has_icon(custom):
                Task.invoke(setattr, self, "display_icon", custom)
                return
            elif custom.startswith("file://"):
                path = Path(ROOT, uri_decode(custom))
            else:
                if custom.startswith("/"):
                    path = Path(ROOT, custom)
                else:
                    path = GLib.canonicalize_filename(custom, get_parent(self.path))
            if path.endswith(".svg"): Task.invoke(setattr, self, "display_icon", Gtk.IconPaintable.new_for_file(Gio.File.new_for_path(path), 1, 1))
            else: Task.invoke(setattr, self, "display_icon", Gio.File.new_for_path(path))
            return
        img = self.content_type.startswith(("image/", "video/")) if self.has_attribute("standard::content-type") and self.content_type and Gio.Application.get_default() and Gio.Application.get_default().lookup_action("thumbnails") and Gio.Application.get_default().lookup_action("thumbnails").get_state().unpack() else False
        if img and not hasattr(Thumbnailer, "paintables") and not Thumbnailer.init():
            Task.invoke(setattr, self, "display_icon", self.icon)
            return
        if self.path.endswith(".svg"):
            Task.invoke(setattr, self, "display_icon", Gtk.IconPaintable.new_for_file(Gio.File.new_for_path(self.path), 1, 1))
            return
        elif img and self.icon:
            if self.path in Thumbnailer.paintables:
                Task.invoke(setattr, self, "display_icon", Thumbnailer.paintables[self.path])
                return
            else:
                Thumbnailer.add_task(self.path)
                return
        if self.path in (MAIN_HOME, HOME):
            Task.invoke(setattr, self, "display_icon", "user-home")
            return
        Task.invoke(setattr, self, "display_icon", self.icon)

    def set_image_icon(self, image):
        r = self.display_icon
        if isinstance(r, str): Task.invoke(image.set_from_icon_name, r)
        elif isinstance(r, Gio.File): Task.invoke(image.set_from_file, r.get_path())
        elif isinstance(r, Gdk.Paintable): Task.invoke(image.set_from_paintable, r)
        elif isinstance(r, Gio.Icon): Task.invoke(image.set_from_gicon, r)
        else: Task.invoke(image.set_from_icon_name, "image-missing-symbolic")

Info.files = List(Info, "path")
Info.alphabetical_sort = Gtk.StringSorter(expression=Gtk.PropertyExpression.new(Info, None, "path"))
Info.content_type_sort = Gtk.StringSorter(expression=Gtk.PropertyExpression.new(Info, None, "content-type"))
Info.modified_sort = Gtk.NumericSorter(expression=Gtk.ClosureExpression.new(int, Info.modified_expression, None))
Info.size_sort = Gtk.NumericSorter(expression=Gtk.PropertyExpression.new(Info, None, "size"))

class View(Gtk.Overlay):
    __gtype_name__ = "View"
    path = GObject.Property(type=str)

    any_filter = Gtk.FileFilter()
    any_filter.add_pattern("*")
    folder_filter = Gtk.FileFilter()
    folder_filter.add_mime_type("inode/directory")
    filters = GObject.Property(type=Gtk.AnyFilter)
    sorter = GObject.Property(type=Gtk.Sorter)

    info = GObject.Property(type=Info)

    selection = GObject.Property(type=Gtk.SelectionModel)

    extra_status = GObject.Property(type=Adw.StatusPage)
    empty_status = GObject.Property(type=Adw.StatusPage)
    no_results_status = GObject.Property(type=Adw.StatusPage)

    columnview = GObject.Property(type=Gtk.ColumnView)
    gridview = GObject.Property(type=Gtk.GridView)

    spinner = GObject.Property(type=Adw.Spinner)
    search = GObject.Property(type=str)

    changing = GObject.Property(type=bool, default=False)
    cancellable = GObject.Property(type=Gio.Cancellable)

    def __init__(self, multiple=True, path="", root=None, columnview=False):
        super().__init__(css_name="view")
        self.spinner = Adw.Spinner(visible=False)
        self.add_overlay(self.spinner)
        self.cancellable = Gio.Cancellable()
        self.connect("notify::path", self.__class__.path_changed)
        self.connect("notify::search", self.__class__.search_changed)
        self.extra_status = Adw.StatusPage(visible=False)
        self.no_results_status = Adw.StatusPage(visible=False, title="No Results", icon_name="edit-find-symbolic")
        self.empty_status = Adw.StatusPage(visible=False)
        self.add_overlay(self.no_results_status)
        self.add_overlay(self.empty_status)
        self.add_overlay(self.extra_status)
        self.selection = Gtk.MultiSelection() if multiple else Gtk.SingleSelection(can_unselect=True, autoselect=False)
        filters = Gtk.EveryFilter()
        f = Gtk.BoolFilter(expression=Gtk.ClosureExpression.new(bool, self.__class__.child_filter_expression, [Gtk.PropertyExpression.new(self.__class__, Gtk.ObjectExpression.new(self), "info"), Gtk.PropertyExpression.new(self.__class__, Gtk.ObjectExpression.new(self), "search")]))
        filters.append(f)
        self.filters = Gtk.AnyFilter()
        self.filters.append(self.__class__.folder_filter)
        self.filters.append(self.__class__.any_filter)
        filters.append(self.filters)
        filter = Gtk.FilterListModel(filter=filters)
        sort = Gtk.SortListModel(model=filter)
        self.bind_property("sorter", sort, "sorter", DEFAULT_BIND)
        self.selection.set_model(sort)
        if columnview:
            self.columnview = Gtk.ColumnView(enable_rubberband=True, model=self.selection)
            for k, v in ColumnItem.columns.items():
                c = Gtk.ColumnViewColumn.new(k, v)
                c.set_properties(expand=True, resizable=True)
                self.columnview.append_column(c)
            self.columnview.action_set_enabled("list.select-all", False)
            self.columnview.connect("activate", self.__class__.selection_activate)
            self.columnview.set_css_classes(["navigation-sidebar"])
            sw = Gtk.ScrolledWindow(child=self.columnview)
        else:
            self.gridview = Gtk.GridView(enable_rubberband=True, max_columns=50, model=self.selection, factory=GridItem.factory)
            self.gridview.action_set_enabled("list.select-all", False)
            self.gridview.connect("activate", self.__class__.selection_activate)
            self.gridview.set_css_classes([])
            sw = Gtk.ScrolledWindow(child=self.gridview)
        self.spinner.bind_property("visible", sw, "visible", INVERT_BIND)
        self.set_child(sw)
        if hasattr(root, "setup_filters"): root.setup_filters(self)
        self.selection.connect("notify::n-items", self.__class__.sync_status, self)
        Task.invoke(setattr, self, "path", path)

    @staticmethod
    def selection_activate(g, p):
        self = g.get_ancestor(View)
        if not self: return
        info = self.selection.get_item(p)
        if not info: return
        self = self.get_root()
        if not self: return
        if self.standalone and hasattr(self, "double_click") and self.double_click(info): return
        if info.is_dir or info.is_archive or info.is_dir_link:
            g.get_ancestor(Tab).path = info.path
            g.get_ancestor(Tab).load()
        elif not info.is_archive: Context.action(widget=g.get_ancestor(View), action="Open")

    def is_selected(self, item):
        s = self.find(item.path)
        return self.selection.is_selected(s) if s != None else False

    def select(self, item, unselect=False):
        n = self.find(item.path)
        if n != None: self.selection.select_item(n, unselect)

    def find(self, path):
        n = self.selection.get_property("n-items")
        for i in range(n):
            s = self.selection.get_item(i).path
            if s == path: return i

    def path_changed(self, p=None, load=True):
        if not self.path:
            Task.invoke(setattr, self, "path", "/")
            return
        self.info = Info(path=self.path) if self.path else None
        if load: self.load()

    def search_changed(self, p=None): self.load()

    @staticmethod
    def child_filter_expression(i, info, search):
        path = info.path
        if info.is_archive and i.is_archived:
            path = path.rstrip("/") + "|/"
            if not i.path.startswith(path): return False
            if search: return search.lower() in i.path.lower()
            else: return not "/" in i.path.split(path, 1)[-1].rstrip("/")
        else:
            path = path.rstrip("/") + "/"
            if (not i.path.startswith(path)) or (i.path.rstrip("/") == path.rstrip("/")): return False
            if search: return search.lower() in i.path.lower()
            else: return not "/" in i.path.split(path, 1)[-1].rstrip("/")

    def load(self):
        self.selection.get_model().get_model().set_model(None)
        for i in self: i.set_visible(i == self.spinner)
        self.changing = True
        self.cancellable.cancel()
        cancellable = self.cancellable = Gio.Cancellable()
        def on_cancel():
            if hasattr(cancellable, "event"):
                cancellable.event.set()
                del cancellable.event
        self.cancellable.connect(on_cancel)
        Task(self.do_load).start()

    def do_load(self):
        extra = False
        if self.info.is_archive or self.info.is_archived or "|/" in self.path and exists(Info.get_archive(self.path, e=True)):
            archive = Info(path=self.path if self.info.is_archive else Info.get_archive(self.info.path, True))
            if archive.exists:
                d = getattr(archive, "archive_modified", None)
                if not (d and d == archive.modification.to_unix()):
                    e, s, m, folders, files, items = self.__class__.archive_get_files(zipfile.ZipFile(archive.path, mode="r") if archive.content_type == "application/zip" else tarfile.open(archive.path, mode="r"), archive.path)
                    if e:
                        for i in files + folders:
                            path = f"{archive.path}|{GLib.DIR_SEPARATOR_S}{i.filename if isinstance(i, zipfile.ZipInfo) else i.name if isinstance(i, tarfile.TarInfo) else ''}"
                            d = (hasattr(i, "is_dir") and i.is_dir()) or (hasattr(i, "isdir") and i.isdir())
                            info = Info(path=path, is_archived=True, size=i.size if hasattr(i, "size") else i.file_size, modification=GLib.DateTime.new_from_unix_utc(i.mtime) if hasattr(i, "mtime") else GLib.DateTime.new(GLib.TimeZone.new_local(), *i.date_time), content_type="inode/directory" if d else Gio.content_type_guess(path)[0], file_type=Gio.FileType.DIRECTORY if d else Gio.FileType.REGULAR)
                        archive.archive_modified = archive.modification.to_unix()
                    else:
                        extra = True
            else:
                extra = True
        elif self.info and self.info.is_dir or self.info.is_dir_link:
            try:
                Info.parse_dir(self.path, search=self.search.lower() if self.search else False, cancellable=self.cancellable)
            except Exception as e:
                if self.search: Task.invoke(Toast, str(e).split("g-io-error-quark:", 1)[-1])
                else:
                    if "Permission denied" in str(e):
                        extra = ("Permission Denied", "view-conceal-symbolic")
        else:
            extra = True
        if extra:
            if isinstance(extra, tuple): self.extra_status.set_properties(title=extra[0], icon_name=extra[1])
            else: self.extra_status.set_properties(title="Not a Folder", icon_name="dialog-error-symbolic")
        if self.cancellable.is_cancelled(): return
        Task.invoke(Info.files.replace, [i for i in Info.files if not i.path.startswith(self.path) or i.is_archived or i.exists])
        Task.invoke(self.selection.get_model().get_model().set_model, Info.files)
        Task.invoke(self.spinner.set_visible, False)
        Task.invoke(setattr, self, "sorter", Info.get_sorter())
        self.changing = False
        Task.invoke(self.sync_status, extra=extra)
        if self.get_root():
            Task.invoke(self.get_parent().sync)
            Tab.idle_save_all()
            if hasattr(self.get_root(), "handle_load"): Task.invoke(self.get_root().handle_load)

    @staticmethod
    def archive_get_files(f, path, return_all=False):
        folders, dirs, files, items = [], [], [], []
        for i in (f.getmembers() if isinstance(f, tarfile.TarFile) else f.infolist()):
            if (i.isdir() if isinstance(f, tarfile.TarFile) else i.is_dir()): folders.append(i)
            else:
                if isinstance(f, tarfile.TarFile):
                    if SEPARATOR in i.path:
                        parent = get_parent(i.path if isinstance(f, tarfile.TarFile) else i.filename)
                        if not parent in dirs: dirs.append(parent)
                files.append(i)
        if isinstance(f, tarfile.TarFile):
            for i in [i for i in dirs if SEPARATOR in i]:
                while True:
                    i = get_parent(i)
                    if SEPARATOR in i and not i in dirs: dirs.append(i)
                    else: break
        if isinstance(f, tarfile.TarFile):
            for i in dirs:
                if isinstance(i, str):
                    i = tarfile.TarInfo(i.strip(SEPARATOR))
                    i.type = tarfile.DIRTYPE
                    i.size = sum(it.size for it in files if it.name.startswith(i.name))
                    if not any(it.path == i.path for it in folders): folders.append(i)
        else:
            for i in folders:
                i.file_size = sum(it.file_size for it in files if it.filename.startswith(i.filename))
        file = Info.archive_get(path)
        file = "" if file == path else file.strip(SEPARATOR)
        size = modified = 0
        if isinstance(f, tarfile.TarFile):
            exists = not file or file and any(i.name.strip(SEPARATOR) == file for i in (files + folders))
        else:
            exists = not file or file and any(i.filename.strip(SEPARATOR) == file for i in (files + folders))
        if exists:
            folder = next(iter((i.name if isinstance(i, tarfile.TarInfo) else i.filename).strip(SEPARATOR) for i in folders if (i.name if isinstance(i, tarfile.TarInfo) else i.filename).strip(SEPARATOR) == file), False)
            for i in folders + files:
                n = (i.name if isinstance(i, tarfile.TarInfo) else i.filename).strip(SEPARATOR)
                p = get_parent(n)
                if file and n == file and not (not return_all and folder == file) or folder and n != folder and p == folder or (not file and not folder and not SEPARATOR in n): items.append(i)
            if return_all and folder:
                for i in [i for i in items if i in folders]:
                    na = (i.name if isinstance(i, tarfile.TarInfo) else i.filename).strip(SEPARATOR)
                    for fi in [it for it in (folders + files) if not it in items]:
                        p = get_parent((fi.name if isinstance(fi, tarfile.TarInfo) else fi.filename).strip(SEPARATOR))
                        if p.startswith(na): items.append(fi)
            if folder:
                i = next(iter(i for i in folders if (i.name if isinstance(i, tarfile.TarInfo) else i.filename).strip(SEPARATOR) == folder), False)
                if i:
                    if isinstance(i, tarfile.TarInfo):
                        size = i.size
                        modified = i.mtime
                    else:
                        size = i.file_size
                        modified = GLib.DateTime.new(GLib.TimeZone.new_local(), *i.date_time).to_unix()
            else:
                size = sum(i.size if isinstance(i, tarfile.TarInfo) else i.file_size for i in files)
        return exists, size, modified, folders, files, items

    def sync_status(self, extra=False, d=None):
        if d:
            self = d
            extra = False
        if self.changing: return
        s = not extra and self.selection.get_n_items() == 0
        self.empty_status.set_properties(visible=s and not self.search, title="Trash Empty" if self.path == TRASH else "No Files", icon_name="user-trash-symbolic" if self.path == TRASH else "folder-symbolic")
        self.no_results_status.set_visible(s and self.search)
        if extra: self.extra_status.set_visible(True)

    def get_items(self):
        n = self.selection.get_property("n-items")
        for i in range(n): yield self.selection.get_item(i)

    def get_selected(self):
        n = self.selection.get_property("n-items")
        for i in range(n):
            if not self.selection.is_selected(i): continue
            yield self.selection.get_item(i)

    def get_all(): return [i.get_child() for i in Tab.get_all() if isinstance(i.get_child(), View)]

class ColumnItem:
    columns = {}
    @staticmethod
    def setup(f, l):
        if getattr(f, "title", "") == "Name":
            image = Gtk.Image()
            Gio.Application.get_default().lookup_action("icon-size").bind_property("state", image, "pixel-size", DEFAULT_BIND, unpack_bind)
            o = Gtk.Overlay(child=image)
            for i in ("cut", "copy"):
                i = Gtk.Image(name=i, halign=Gtk.Align.START, valign=Gtk.Align.START, icon_name=f"edit-{i}-symbolic", visible=False)
                image.bind_property("pixel-size", i, "pixel-size", DEFAULT_BIND, GridItem.action_size_bind)
                o.add_overlay(i)
            box = Gtk.Box(css_name="item-box")
            box.append(o)
            box.append(Gtk.Label(single_line_mode=True, ellipsize=Pango.EllipsizeMode.END))
            l.set_child(box)
        else: l.set_child(Gtk.Label(single_line_mode=True, ellipsize=Pango.EllipsizeMode.END))

    @staticmethod
    def bind(f, l):
        if getattr(f, "title", "") == "Name":
            l.binds = []
            for c in l.get_child():
                if isinstance(c, Gtk.Label): l.get_property("item").bind_property(f.title.lower().replace(" ", "-"), c, "label", DEFAULT_BIND, ColumnItem.column_bind)
                else:
                    for i in c:
                        if i.get_name() in ("cut", "copy"): l.binds.append(l.get_property("item").bind_property(f"is-{i.get_name()}", i, "visible", DEFAULT_BIND))
                        else: l.binds.append(l.get_property("item").bind_property("display-icon", i, "name", DEFAULT_BIND, ColumnItem.icon_bind))
        else:
            l.binds = [l.get_property("item").bind_property(f.title.replace(" Time", "").lower().replace(" ", "-"), l.get_child(), "label", DEFAULT_BIND, ColumnItem.column_bind)]

    @staticmethod
    def icon_bind(b, v):
        Task.invoke(b.get_property("source").set_image_icon, b.get_property("target"))
        return ""

    @staticmethod
    def column_bind(b, v):
        name =  b.get_property("source-property")
        if isinstance(v, GLib.DateTime):
            v = v.to_local().format("%x %T")
        if name == "size":
            v = GLib.format_size(v)
        if name == "content-type":
            v = Gio.content_type_get_description(v)
        return v

    @staticmethod
    def unbind(f, l):
        for i in getattr(l, "binds", []): i.unbind()
        if hasattr(l, "binds"): del l.binds

    @staticmethod
    def teardown(f, l): l.set_child(None)

    for i in ("Name", "Content Type", "Modification Time", "Size"):
        factory = Gtk.SignalListItemFactory.new()
        setattr(factory, "title", i)
        factory.connect("setup", setup)
        factory.connect("bind", bind)
        factory.connect("unbind", unbind)
        factory.connect("teardown", teardown)
        columns[i] = factory

class GridItem(Gtk.Overlay):
    __gtype_name__ = "GridItem"
    info = GObject.Property(type=Info)
    image = GObject.Property(type=Gtk.Image)
    label = GObject.Property(type=Gtk.Label)
    cut = GObject.Property(type=Gtk.Image)
    copy = GObject.Property(type=Gtk.Image)

    def __init__(self, **kwargs):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        super().__init__(css_name="griditem", child=box, **kwargs)
        self.cut, self.copy = [Gtk.Image(halign=Gtk.Align.START, valign=Gtk.Align.START, icon_name=f"edit-{i}-symbolic", visible=False) for i in ("cut", "copy")]
        self.bindings = []
        self.image = Gtk.Image()
        self.label = Gtk.Label(justify=Gtk.Justification.CENTER, halign=Gtk.Align.CENTER, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, ellipsize=Pango.EllipsizeMode.END)
        self.image.bind_property("tooltip-text", self.label, "label", DEFAULT_BIND)
        for i in (self.image, self.label): box.append(i)
        for i in (self.cut, self.copy):
            self.image.bind_property("pixel-size", i, "pixel-size", DEFAULT_BIND, self.__class__.action_size_bind)
            self.add_overlay(i)
        Gio.Application.get_default().lookup_action("icon-size").bind_property("state", self.image, "pixel-size", DEFAULT_BIND, unpack_bind)
        Gio.Application.get_default().lookup_action("show-names").bind_property("state", self.label, "visible", DEFAULT_BIND, unpack_bind)
        self.connect("notify::info", self.__class__.info_changed)
        self.__class__.info_changed(self)

    @staticmethod
    def action_size_bind(b, v): return max(10, v / 6)

    @staticmethod
    def info_changed(self, p=0):
        for i in self.bindings: i.unbind()
        self.bindings = []
        if self.info:
            self.bindings.append(self.info.bind_property("path", self.image, "tooltip-text", DEFAULT_BIND, self.__class__.basename_bind))
            self.bindings.append(self.info.bind_property("is-cut", self.cut, "visible", DEFAULT_BIND))
            self.bindings.append(self.info.bind_property("is-copy", self.copy, "visible", DEFAULT_BIND))
            self.bindings.append(self.info.bind_property("display-icon", self.image, "name", DEFAULT_BIND, ColumnItem.icon_bind))

    @staticmethod
    def basename_bind(b, v): return basename(v) if v else ""

    factory = Gtk.SignalListItemFactory.new()
    @staticmethod
    def setup(f, l): l.set_child(GridItem())
    factory.connect("setup", setup)
    @staticmethod
    def bind(f, l):
        l.get_child().info = l.get_property("item")
    factory.connect("bind", bind)
    @staticmethod
    def unbind(f, l):
        l.get_child().info = None
    factory.connect("unbind", unbind)
    @staticmethod
    def teardown(f, l): l.set_child(None)
    factory.connect("teardown", teardown)

class Context(Gtk.PopoverMenu):
    __gtype_name__ = "Context"

    widget = GObject.Property(type=GObject.Object)

    def __init__(self):
        super().__init__(has_arrow=False, width_request=220)

    @staticmethod
    def activate(a, s): Context.action(widget=a.window.context.widget if a.window.context else None, action=s.unpack().strip("'"))

    @staticmethod
    def action(widget=None, action=""):
        if action == "Open Trash":
            Tab(path=TRASH)
            return
        if action.startswith("Icon "):
            a = Gio.Application.get_default().lookup_action("icon-size")
            a.set_state(get_variant(a.get_state().unpack() + (-2 if "Smaller" in action else 2)))
            return
        if not hasattr(widget, "info") or not action: return
        if widget.get_root().entry_prompt.get_mapped(): widget.get_root().entry_prompt.close()
        if action == "Reload":
            if widget.get_ancestor(Tab): widget.get_ancestor(Tab).load(history=True)
            return
        view = widget if isinstance(widget, View) else widget.get_ancestor(View)
        if not view: return
        if action == "Unselect All": return view.selection.unselect_all()
        if action == "Select All": return view.selection.select_all()
        infos = [i for i in view.get_selected()]
        if not infos: infos.append(widget.info)
        widget.get_root().prompt.infos = widget.get_root().entry_prompt.infos = infos
        if action.startswith("Open"):
            if "in New Tab" in action:
                for i in infos: Tab(path=i.path)
            else:
                for i in infos: launch(display(i.path))
            return
        if action.startswith("New "):
            widget.get_root().entry_prompt.infos = [view.info]
            widget.get_root().entry_prompt.set_heading(action)
            widget.get_root().entry_prompt.present(widget.get_root())
            widget.get_root().entry_prompt.get_extra_child().set_text(action)
            return widget.get_root().entry_prompt.get_extra_child().set_position(-1)
        if action == "Rename":
            widget.get_root().entry_prompt.set_heading(f"Rename {basename(infos[0].get_name()) if len(infos) == 1 else str(len(infos)) + ' files'}")
            widget.get_root().entry_prompt.present(widget.get_root())
            widget.get_root().entry_prompt.get_extra_child().set_text(basename(infos[0].path))
            return widget.get_root().entry_prompt.get_extra_child().set_position(-1)
        if action == "Delete":
            widget.get_root().prompt.set_heading(f"Delete {basename(infos[0].path) if len(infos) == 1 else str(len(infos)) + ' files'}")
            return widget.get_root().prompt.present(widget.get_root())
        if action == "Trash":
            make_dirs(TRASH)
            tf = Gio.File.new_for_path(TRASH)
            for i in infos: Operation.move(i.path, unique_name(i.get_name(), tf).get_path())
        if action.endswith(" to"):
            action = action.split(" to", 1)[0]
            return Gtk.FileDialog(title=f"{action.rstrip('e')}ing {(str(len(infos)) + ' files') if len(infos) > 1 else infos[0].path}").select_folder(Window.current, None, Operation.do_dialog, (action, infos))
        if action in ("Copy", "Cut") and infos:
            infos = [i for i in infos if i != view.info]
            if action == "Cut" and view.info.is_archived:
                action = "Copy"
            Gdk.Display.get_default().get_clipboard().set(Gdk.FileList.new_from_list([Gio.File.new_for_path(display(i.path)) for i in infos]) if infos else "")
            for i in Info.files:
                i.is_copy = i.is_cut = False
            for i in infos: setattr(i, f"is_{action.lower()}", True)
        if action == "Paste" and view.info and not view.info.is_archived and view.info.exists:
            f = Gio.File.new_for_path(view.path)
            for i in Info.files:
                if not (i.is_archived or i.exists): continue
                if i.is_cut: Operation.move(i.path, unique_name(i.get_name(), f).get_path())
                elif i.is_copy: Operation.copy(i.path, unique_name(i.get_name(), f).get_path())
        if action == "Properties": return Properties(widget.get_root(), infos)
        if action == "Compress": return Compress(view.path, infos)

class Compress(Prompt):
    __gtype_name__ = "Compress"

    path = GObject.Property(type=str)
    archive_name = GObject.Property(type=Adw.EntryRow)
    archive_type = GObject.Property(type=Adw.ComboRow)
    password = GObject.Property(type=Gtk.PasswordEntry)

    def __init__(self, path, infos):
        self.infos = infos
        group = Gtk.ListBox(css_classes=("boxed-list", "main"), selection_mode=Gtk.SelectionMode.NONE)
        super().__init__(heading=f"Compress {len(infos)} file{'s' if len(infos) > 1 else ''}", extra_child=group, callback=self.__class__.do)
        self.path = path
        self.add_css_class("compress")
        self.archive_name = Adw.EntryRow(title="Name", text=basename(infos[0].path) if len(infos) == 1 else "archive")
        self.archive_type = Adw.ComboRow(title="Type", model=Gtk.StringList.new(["TAR", "ZIP"]))
        self.password = Gtk.PasswordEntry(placeholder_text="Password", show_peek_icon=True)
        for i in [self.archive_name, self.archive_type, self.password]: group.append(i)
        self.archive_type.bind_property("selected-item", self.password.get_parent(), "visible", DEFAULT_BIND, self.__class__.password_bind)
        self.present()
        self.archive_name.grab_focus()
        self.archive_name.select_region(0, 0)
        self.archive_name.set_position(-1)

    @staticmethod
    def password_bind(b, v): return v.get_string() == "NONE"

    @staticmethod
    def do(self):
        n = self.archive_name.get_text()
        t = self.archive_type.get_selected_item().get_string()
        p = self.password.get_text()
        self.password = self.archive_type = self.archive_name = None
        archive = Path(self.path, n + (".zip" if t == "ZIP" else ".tar.xz"))
        infos = self.infos
        del self.infos
        self.path = ""
        Task(Operation.compress, archive, [i.path for i in infos], t).start()

class ProgressReader:
    def __init__(self, src, size, on_read):
        self.v = src
        self.remaining = size
        self.callback = on_read
        self.processed = 0

    def read(self, n=-1):
        if self.remaining <= 0:
            return b""
        if n < 0 or n > self.remaining:
            n = self.remaining

        chunk = self.v.read(n)
        if not chunk:
            return b""

        self.remaining -= len(chunk)
        self.processed += len(chunk)
        self.callback(self.processed)
        return chunk

class Operation(ListObject):
    __gtype_name__ = "Operation"
    type = GObject.Property(type=str)
    cancelled = GObject.Property(type=bool, default=False)
    files = GObject.Property(type=List)
    progress = GObject.Property(type=float)
    can_undo = GObject.Property(type=bool, default=False)

    def __init__(self, operation, files=None):
        super().__init__(type=operation, files=List(Gtk.StringObject))
        self.can_undo = self.type in ("New File", "New Link", "New Folder", "Copy", "Compress", "Extract", "Rename", "Move", "Trash")
        if files: self.files.extend(files)
        Operations.list.prepend(self)

    def cancel(self):
        self.cancelled = True
        Operations.list.remove(self)

    def undo(self):
        self.cancel()
        if self.type in ("New File", "New Link", "New Folder", "Copy", "Compress", "Extract"):
            f = self.files[-1].get_string()
            if exists(f): delete(f)
            self.reload_tabs(type="Delete", files=[f])
        if self.type in ("Rename", "Move", "Trash"): Task.invoke(Operation.move, self.files[1].get_string(), self.files[0].get_string())

    @staticmethod
    def copy(a, b):
        self = Operation(operation="Copy", files=[a, b])
        Task(self.do_copy).start()

    def do_copy(self, chunk_size=1024 * 1024, callback=None):
        old, new = self.files[0].get_string(), self.files[1].get_string()
        free = disk_usage(get_parent(new)).free
        archive, file = Info.get_archive(old), Info.archive_get(old)
        if archive and file and archive != file and archive != old:
            self.type = "Extract"
            if tarfile.is_tarfile(archive):
                f = tarfile.open(archive, mode="r")
            else:
                f = zipfile.ZipFile(archive, mode="r")
            ba = basename(new)
            files = {}
            total = 0
            for i in View.archive_get_files(f, old, return_all=True)[-1]:
                n = (i.filename if isinstance(i, zipfile.ZipInfo) else i.name)
                nf = new if n == file else Path(new, n.split(ba, 1)[-1].strip(SEPARATOR))
                if (isinstance(i, zipfile.ZipInfo) and i.is_dir()) or (isinstance(i, tarfile.TarInfo) and i.isdir()): make_dirs(nf)
                else:
                    total += i.size if hasattr(i, "size") else i.file_size
                    files[nf] = f.open(i) if isinstance(i, zipfile.ZipInfo) else f.extractfile(i)
            copied = 0
            for k, v in files.items():
                make_dirs(get_parent(k))
                with open(k, "wb") as dst:
                    while chunk := v.read(chunk_size):
                        if self.cancelled: return
                        dst.write(chunk)
                        copied += len(chunk)
                        Task.invoke(setattr, self, "progress", copied / total if total else 1)
                v.close()
            f.close()
        elif is_dir(old):
            dirs = {}
            files = {}
            for r, d, f in walk(old):
                for i in d:
                    path = Path(r, i)
                    dirs[path] = ""
                for i in f:
                    path = Path(r, i)
                    files[path] = open(path, "rb")
            total = sum(fstat(i.fileno()).st_size for i in files.values())
            if total > free:
                Toast(f"Can't copy {new}. There is only {GLib.format_size(free)} left. Needs {GLib.format_size(total)}")
                return self.cancel()
            copied = 0
            for k, v in files.items():
                path = Path(new, k.split(old, 1)[-1])
                make_dirs(get_parent(path))
                with open(path, "wb") as dst:
                    while chunk := v.read(chunk_size):
                        if self.cancelled: return
                        dst.write(chunk)
                        copied += len(chunk)
                        Task.invoke(setattr, self, "progress", copied / total if total else 1)
                v.close()
            for i in dirs: make_dirs(Path(new, i.split(old, 1)[-1]))
        else:
            with open(old, "rb") as src, open(new, "wb") as dst:
                total = fstat(src.fileno()).st_size
                if total > free:
                    Toast(f"Can't copy {new}. There is only {GLib.format_size(free)} left. Needs {GLib.format_size(total)}")
                    return self.cancel()
                copied = 0
                while chunk := src.read(chunk_size):
                    if self.cancelled: return
                    dst.write(chunk)
                    copied += len(chunk)
                    Task.invoke(setattr, self, "progress", copied / total if total else 1)
        Window.data_init()
        if Window.data.exists(table="Icons", conditions="Path = ?", conds=(old,)):
            v = Window.data.read(table="Icons", column="Icon", conditions="Path = ?", conds=(old,))
            Window.data.set_default(table="Icons", conditions="Path = ?", conds=(new,), values=(new, v))
        if callback: callback()
        self.reload_tabs()

    @staticmethod
    def new_file(f):
        if exists(f): return Toast(f"{f} already exists!")
        self = Operation(operation="New File", files=[f])
        set_contents(f)
        self.progress = 1
        self.reload_tabs()

    @staticmethod
    def new_folder(f):
        if exists(f): return Toast(f"{f} already exists!")
        self = Operation(operation="New Folder", files=[f])
        make_dirs(f)
        self.progress = 1
        self.reload_tabs()

    @staticmethod
    def new_link(f):
        if exists(f): return Toast(f"{f} already exists!")
        self = Operation(operation="New Link", files=[f])
        Gio.File.new_for_path(f).make_symbolic_link("link")
        self.progress = 1
        self.reload_tabs()

    @staticmethod
    def move(a, b):
        make_dirs(get_parent(b))
        self = Operation(operation="Trash" if b.startswith(TRASH) else "Rename" if get_parent(a) == get_parent(b) else "Move", files=[a, b])
        try:
            different = stat(a).st_dev != stat(get_parent(b)).st_dev
        except:
            different = False
        if different:
            def do_finish():
                delete(a)
                self.progress = 1
            Task(self.do_copy, callback=do_finish).start()
        else:
            Gio.File.new_for_path(a).move(Gio.File.new_for_path(b), Gio.FileCopyFlags.NOFOLLOW_SYMLINKS)
            Window.data_init()
            if Window.data.exists(table="Icons", conditions="Path = ?", conds=(a,)):
                v = Window.data.read(table="Icons", column="Icon", conditions="Path = ?", conds=(a,))
                Window.data.set_default(table="Icons", conditions="Path = ?", conds=(b,), values=(b, v))
                Window.data.delete(table="Icons", conditions="Path = ?", conds=(a,))
            self.progress = 1
            self.reload_tabs()

    @staticmethod
    def delete(f):
        self = Operation(operation="Delete", files=[f])
        if exists(f): delete(f)
        self.progress = 1
        self.reload_tabs()

    @staticmethod
    def compress(a, pp, t):
        self = Operation(operation="Compress", files=[a] + pp)
        Task(self.do_compress, t).start()

    def do_compress(self, t, chunk_size=1024 * 1024):
        l = [i.get_string() for i in self.files]
        dirs = {}
        files = {}
        for i in l[1:]:
            if is_dir(i):
                root = i
                for r, d, f in walk(i):
                    for it in d:
                        path = Path(r, it)
                        dirs[path] = path.split(root, 1)[-1].lstrip("/")
                    for it in f:
                        path = Path(r, it)
                        files[path.split(root, 1)[-1].lstrip("/")] = open(path, "rb")
            else:
                files[basename(i)] = open(i, "rb")
        total = sum(fstat(i.fileno()).st_size for i in files.values())
        processed = 0
        if t == "ZIP":
            with zipfile.ZipFile(l[0], mode="w", compression=zipfile.ZIP_ZSTANDARD) as file:
                for i in dirs.values(): file.mkdir(i)
                for k, v in files.items():
                    if self.cancelled: return
                    with file.open(k, "w") as dst:
                        while chunk := v.read(chunk_size):
                            if self.cancelled: return
                            dst.write(chunk)
                            processed += len(chunk)
                            Task.invoke(setattr, self, "progress", processed / total if total else 1)
                    v.close()
        if t == "TAR":
            with tarfile.open(l[0], mode="w:xz") as file:
                for i in dirs.values():
                    info = tarfile.TarInfo(i.rstrip("/") + "/")
                    info.type = tarfile.DIRTYPE
                    file.addfile(info)
                for k, v in files.items():
                    if self.cancelled: return
                    size = fstat(v.fileno()).st_size
                    info = tarfile.TarInfo(k)
                    info.size = size
                    def f(progress): Task.invoke(setattr, self, "progress", progress / total if total else 1)
                    file.addfile(info, fileobj=ProgressReader(v, size, f))
                    v.close()
        self.reload_tabs()

    def reload_tabs(self, type=None, files=None):
        type = type or self.type
        files = files or [i.get_string() for i in self.files]
        tabs = {}
        for i in Tab.get_all():
            if i.get_child() and not i.path in tabs:
                tabs[i.path] = i
        for i in tabs.values():
            do = type.startswith(("New", "Compress", "Delete")) and has_parent(files[0], i.path)
            do = do or type in ("Copy", "Move", "Trash", "Rename", "Extract") and has_parent(files[1], i.path)
            do = do or type in ("Move", "Trash", "Rename") and has_parent(files[0], i.path)
            if do: Task.invoke(i.load, True)

    @staticmethod
    def do_dialog(d, r, da):
        try:
            f = d.select_folder_finish(r)
        except: return
        action, infos = da
        for i in infos:
            if action == "Move": Operation.move(i.path, unique_name(i.get_name(), f).get_path())
            if action == "Copy": Operation.copy(i.path, unique_name(i.get_name(), f).get_path())

class OperationItem(Gtk.Box):
    __gtype_name__ = "OperationItem"
    operation = GObject.Property(type=Operation)
    progress = GObject.Property(type=Gtk.ProgressBar)
    label = GObject.Property(type=Gtk.Label)
    image = GObject.Property(type=Gtk.Image)
    undo = GObject.Property(type=Gtk.Button)
    def __init__(self):
        super().__init__(css_name="operation", orientation=Gtk.Orientation.VERTICAL)
        self.bindings = []
        self.connect("notify::operation", self.__class__.operation_changed)
        box = Gtk.Box(hexpand=True)
        self.image = Gtk.Image(css_classes=["circular"])
        box.append(self.image)
        self.label = Gtk.Label(hexpand=True, single_line_mode=True, ellipsize=Pango.EllipsizeMode.END)
        self.label.bind_property("label", self.label, "tooltip-text", DEFAULT_BIND)
        box.append(self.label)
        self.undo = Button(tooltip_text="Undo", icon_name="edit-undo", css_classes=["circular"], callback=self.__class__.undo)
        box.append(self.undo)
        box.append(Button(tooltip_text="Remove", icon_name="process-stop", css_classes=["circular"], callback=self.__class__.remove))
        self.append(box)
        self.progress = Gtk.ProgressBar()
        self.progress.bind_property("fraction", self.progress, "visible", DEFAULT_BIND, self.__class__.progress_bind)
        self.append(self.progress)

    @staticmethod
    def operation_changed(self, p=None):
        for i in self.bindings: i.unbind()
        self.bindings = []
        if self.operation:
            self.bindings.append(self.operation.bind_property("progress", self.progress, "fraction", DEFAULT_BIND))
            self.bindings.append(self.operation.bind_property("progress", self.label, "label", DEFAULT_BIND, self.__class__.label_bind))
            self.bindings.append(self.operation.bind_property("type", self.image, "icon-name", DEFAULT_BIND, self.__class__.icon_bind))
            self.bindings.append(self.operation.bind_property("can-undo", self.undo, "visible", DEFAULT_BIND))


    @staticmethod
    def icon_bind(b, v):
        if v == "Extract": return "system-file-manager-symbolic"
        if v == "Compress": return "system-file-manager-symbolic"
        if v == "Move": return "network-transmit-receive-symbolic"
        if v == "Rename": return "document-edit-symbolic"
        if v == "Trash": return "user-trash-full-symbolic"
        if v == "Delete": return "edit-delete-symbolic"
        if v == "Copy": return "edit-copy-symbolic"
        if v == "New Folder": return "folder-new-symbolic"
        if v == "New File": return "document-new-symbolic"
        if v == "New Link": return "document-revert-symbolic"

    @staticmethod
    def label_bind(b, v):
        o = b.get_property("source")
        f = [display(i.get_string()) for i in o.files]
        if o.type in ("New File", "New Folder", "New Link"): return f"Created {f[0]}"
        if o.type == "Extract": return f"Extract{'ing' if v != 1 else 'ed'} {f[0]} -> {f[-1]}"
        if o.type == "Compress": return f"Compress{'ing' if v != 1 else 'ed'} {f[0]}"
        if o.type == "Delete": return f"Delet{'ing' if v != 1 else 'ed'} {f[0]}"
        if o.type == "Rename": return f"Renamed {f[0]} -> {f[1]}"
        if o.type == "Move": return f"Moved {f[0]} -> {f[1]}"
        if o.type == "Trash": return f"Trashed {f[0]}"
        if o.type == "Copy": return f"Cop{'ying' if v != 1 else 'ied'} {f[0]} -> {f[1]}"

    @staticmethod
    def progress_bind(b, v): return v != 1.0

    @staticmethod
    def undo(b):
        self = b.get_ancestor(OperationItem)
        if not self or not self.operation: return
        self.operation.undo()

    @staticmethod
    def remove(b):
        self = b.get_ancestor(OperationItem)
        if not self or not self.operation: return
        self.operation.cancel()

    factory = Gtk.SignalListItemFactory.new()
    @staticmethod
    def setup(f, l): l.set_child(OperationItem())
    factory.connect("setup", setup)
    @staticmethod
    def bind(f, l):
        Task.invoke(l.get_child().get_parent().set_properties, css_classes=[], focusable=False)
        l.get_child().operation = l.get_property("item")
    factory.connect("bind", bind)
    @staticmethod
    def unbind(f, l):
        l.get_child().operation = None
    factory.connect("unbind", unbind)
    @staticmethod
    def teardown(f, l): l.set_child(None)
    factory.connect("teardown", teardown)

class Operations(Gtk.Revealer):
    __gtype_name__ = "Operations"
    list = List(Operation)

    def __init__(self):
        listview = Gtk.ListView(valign=Gtk.Align.START, factory=OperationItem.factory, model=Gtk.NoSelection(model=self.__class__.list))
        listview.set_css_classes(["navigation-sidebar"])
        button = Button(t=Gtk.MenuButton, icon_name="accessories-text-editor", tooltip_text="Operations", popover=Gtk.Popover(autohide=False, child=Gtk.ScrolledWindow(propagate_natural_height=True, child=listview, valign=Gtk.Align.START)))
        super().__init__(transition_duration=300, transition_type=Gtk.RevealerTransitionType.CROSSFADE, child=button, reveal_child=False)
        listview.get_model().bind_property("n-items", self, "reveal-child", DEFAULT_BIND, bool_bind)
        self.add_css_class("operations")
        self.bind_property("reveal-child", self, "visible", DEFAULT_BIND)

class Properties(PopupDialog):
    __gtype_name__ = "Properties"
    group = GObject.Property(type=Adw.PreferencesGroup)
    path = GObject.Property(type=str)
    cancellable = GObject.Property(type=Gio.Cancellable)

    def __init__(self, root, infos):
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.pack_end(PopupDialogButton())
        toolbar.add_top_bar(header)
        super().__init__(content=toolbar, dialog_kwargs={"content_width": 500, "content_height": 434}, window_kwargs={"default_width": 500, "default_height": 434})
        self.cancellable = Gio.Cancellable.new()
        page = GroupsPage()
        self.add_css_class("properties")
        self.group = Adw.PreferencesGroup()
        page.add(self.group)
        size_row = False
        content_type = ""
        if len(infos) == 1:
            self.path = infos[0].path
            t = self.path
            t = Tab.title_bind(v=t)
        else:
            self.path = ""
            t = []
            fs = {"archives": [], "folders": [], "files": []}
            for i in infos:
                if i.is_dir: fs["folders"].append(i)
                elif i.is_archive: fs["archives"].append(i)
                else: fs["files"].append(i)
            for k, v in fs.items():
                if len(v) > 0: t.append(f"{len(v)} {k.rstrip('s') if len(v) == 1 else k}")
            t = human_readable_join(t)
            if all(i.content_type == infos[0].content_type for i in infos):
                content_type = Gio.content_type_from_mime_type(infos[0].content_type)
                content_type = Gio.content_type_get_description(content_type)
                if content_type: self.group.add(LabelRow(title="Content Type", label=content_type))
        if self.path and not infos[0].is_archived and not exists(self.path): toolbar.set_content(Adw.StatusPage(title=f"{self.path} doesn't exist", icon_name="dialog-error-symbolic"))
        else:
            toolbar.set_content(page)
            size_row = True
            if self.path:
                self.group.add(Properties.editable_row(title="Custom Icon", text=infos[0].custom_icon))
                if infos[0].content_type:
                    content_type = Gio.content_type_from_mime_type(infos[0].content_type)
                    content_type = Gio.content_type_get_description(content_type)
                if infos[0].symlink_target:
                    content_type = "Link"
                    size_row = False
                    self.group.add(Properties.editable_row(title="Link Target", text=infos[0].symlink_target))
                self.group.add(Properties.date_row(title="Modification Time", date=infos[0].modification))
                self.group.add(LabelRow(title="Location", label=display(self.path), justify=Gtk.Justification.RIGHT, xalign=1, hexpand=True, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR))
                if content_type: self.group.add(LabelRow(title="Content Type", label=content_type))
        if size_row: Task(self.size_row, content_type, infos).start()
        self.set_title(t)
        self.present(root)

    def do_dispose(self):
        PopupDialog.do_dispose(self)
        self.cancellable.cancel()

    def size_row(self, content_type, infos):
        if self.path:
            if infos[0].is_mountpoint:
                size = disk_usage(self.path)
                Task.invoke(self.group.add, LabelRow(title="Used", label=GLib.format_size(size.used)))
                Task.invoke(self.group.add, LabelRow(title="Free", label=GLib.format_size(size.free)))
                Task.invoke(self.group.add, LabelRow(title="Total", label=GLib.format_size(size.total)))
            elif infos[0].is_dir:
                row = Adw.ActionRow(title="Size")
                spinner = Adw.Spinner()
                row.add_suffix(spinner)
                Task.invoke(self.group.add, row)
                size = GLib.spawn_command_line_sync(f"du -s \"{self.path}\"")[1].decode().strip().rsplit("\n", 1)[-1].split("\t", 1)[0]
                if size.isdigit():
                    size = GLib.format_size(int(size) * 1000)
                if self.cancellable.is_cancelled(): return
                Task.invoke(row.remove, spinner)
                Task.invoke(row.add_suffix, Gtk.Label(label=size))
            else: Task.invoke(self.group.add, LabelRow(title="Size", label=GLib.format_size(infos[0].size)))
        else:
            if any(not i.is_archived and i.is_dir for i in infos):
                row = Adw.ActionRow(title="Size")
                spinner = Adw.Spinner()
                row.add_suffix(spinner)
                Task.invoke(self.group.add, row)
                size = 0
                for i in infos:
                    if not i.is_archived and i.is_dir:
                        s = GLib.spawn_command_line_sync(f"du -s \"{i.path}\"")[1].decode().strip().rsplit("\n", 1)[-1].split("\t", 1)[0]
                        if s.isdigit():
                            size += int(s) * 1000
                    else:
                        size += i.size
                if self.cancellable.is_cancelled(): return
                Task.invoke(row.remove, spinner)
                Task.invoke(row.add_suffix, Gtk.Label(label=GLib.format_size(size)))
            else: Task.invoke(self.group.add, LabelRow(title="Size", label=GLib.format_size(sum(i.size for i in infos))))

    @staticmethod
    def do_edit(row, p=None):
        v = row.get_text() if isinstance(row, Adw.EntryRow) else row.date
        prop = row.get_title()
        self = PopupDialog.get_self(row)
        if not self or not self.path: return
        info = Info(path=self.path)
        if prop in ("Modification Time", "Creation Time"): setattr(info, prop.split(" ", 1)[0].lower(), v)
        if prop == "Link Target":
            info.symlink_target = v
        if prop == "Custom Icon":
            info.custom_icon = v
        i = Gio.FileInfo()
        info.copy_into(i)
        for it in ("standard::type", "standard::is-symlink", "standard::name", "standard::display-name", "standard::content-type", "standard::icon", "standard::size", "time::created", "unix::is-mountpoint"): i.remove_attribute(it)
        Gio.File.new_for_path(self.path).set_attributes_from_info(i, Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS)

    @staticmethod
    def editable_row(title="", text=""):
        e = Adw.EntryRow(title=title, text=text or "", show_apply_button=True)
        e.connect("apply", Properties.do_edit)
        return e

    @staticmethod
    def date_row(title="", date=None):
        e = DateRow(title=title, date=date.to_local())
        e.connect("notify::date", Properties.do_edit)
        return e

class Thumbnailer:
    def init():
        try:
            global Gst
            from gi.repository import Gst
        except:
            Gst = False
        if not Gst: return
        if not Gst.is_initialized(): Gst.init()
        Thumbnailer.doing = False
        Thumbnailer.tasks = []
        Thumbnailer.paintables = {}
        return True

    @staticmethod
    def invalidate_contents(p, pipeline):
        if not hasattr(p, "duration"):
            p.duration = pipeline.query_duration(Gst.Format.TIME)[-1]
            if p.duration > 1 * Gst.SECOND:
                pipeline.seek_simple(Gst.Format.TIME, Gst.SeekFlags.ACCURATE | Gst.SeekFlags.FLUSH, p.duration / 2)
                return
        current = pipeline.get_by_name("File").get_property("location")
        p.disconnect(p.sig)
        del p.sig
        del p.duration
        p = p.get_current_image()
        Thumbnailer.paintables[current] = p
        if current in Thumbnailer.tasks: Thumbnailer.tasks.remove(current)
        for i in Info.files:
            if i: Task.invoke(i.do_icon)
        Task.invoke(MediaStream.destroy_pipeline, pipeline)
        Task.invoke(Thumbnailer.do)

    @staticmethod
    def remove(c):
        if Thumbnailer.tasks and c == Thumbnailer.tasks[0] and Thumbnailer.doing:
            print("Thumbnailer", c, "failed")
            Thumbnailer.doing = False
            Thumbnailer.tasks.remove(c)
            Task.invoke(Thumbnailer.do)
        return False

    @staticmethod
    def do():
        self = Thumbnailer
        Gst.init()
        if self.tasks:
            c = self.tasks[0]
            GLib.timeout_add(3000, self.remove, c)
        if not self.tasks:
            self.doing = False
            return False
        if not exists(c): return False
        self.doing = True
        pipeline = Gst.parse_bin_from_description(f'decodebin3 async_handling=false message_forward=false name=Decode ! videoscale ! video/x-raw,width=[1,360],height=[1,360],pixel-aspect-ratio=1/1 ! gtk4paintablesink name=Sink qos=false sync=false async=false')
        file = Gst.ElementFactory.make("filesrc", "File")
        file.set_property("location", c)
        pipeline.add(file)
        file.link(pipeline.get_by_name("Decode"))
        pipeline.set_bus(None)
        pipeline.set_properties(async_handling=False, message_forward=False)
        p = pipeline.get_by_name("Sink").get_property("paintable")
        p.sig = p.connect("invalidate-contents", self.invalidate_contents, pipeline)
        pipeline.set_state(Gst.State.PLAYING)
        return False

    @staticmethod
    def add_task(path):
        if not hasattr(Thumbnailer, "paintables") and not Thumbnailer.init(): return
        if not path in Thumbnailer.tasks: Thumbnailer.tasks.append(path)
        if not Thumbnailer.doing:
            Thumbnailer.doing = True
            Task.invoke(Thumbnailer.do)

class FileDialog(Window):
    __gtype_name__ = "FileDialog"
    accept_label = GObject.Property(type=str)
    default_filter = GObject.Property(type=Gtk.FileFilter)
    filters = GObject.Property(type=Gio.ListModel)
    initial_file = GObject.Property(type=Gio.File)
    initial_folder = GObject.Property(type=Gio.File)
    initial_name = GObject.Property(type=str)
    modal = GObject.Property(type=bool, default=True)

    extra_menu = GObject.Property(type=Gio.MenuModel)

    operation = GObject.Property(type=str)
    options = GObject.Property(type=Gio.MenuModel)
    controls = GObject.Property(type=Gtk.WindowHandle)
    title_widget = GObject.Property(type=Adw.WindowTitle)
    entry = GObject.Property(type=Gtk.Entry)

    def __init__(self, title="", **kwargs):
        super().__init__(title=title or "File Dialog", standalone=True)
        for k, v in kwargs.items(): setattr(self, k, v)
        variant = get_variant("")
        self.add_action(Gio.SimpleAction.new_stateful("filter", variant.get_type(), variant))
        self.lookup_action("filter").connect("notify::state", self.__class__.filter_changed, self)
        self.controls = Gtk.WindowHandle(child=Gtk.Box(css_name="controls-box"))
        self.multi.set_child("controls", self.controls)
        self.controls.get_child().append(Button(can_shrink=True, callback=self.__class__.button_close, label="Close"))
        self.title_widget = Adw.WindowTitle(halign=Gtk.Align.CENTER, hexpand=True)
        self.controls.get_child().append(self.title_widget)
        self.bind_property("title", self.title_widget, "title", DEFAULT_BIND)
        self.entry = Gtk.Entry(xalign=0.50, hexpand=True)
        self.controls.get_child().append(self.entry)
        self.bind_property("initial-name", self.entry, "text", DEFAULT_BIND)
        self.bind_property("title", self.entry, "placeholder-text", DEFAULT_BIND)
        self.entry.bind_property("visible", self.title_widget, "visible", INVERT_BIND)
        b = Button(can_shrink=True, callback=self.__class__.button_accept)
        self.bind_property("accept-label", b, "label", DEFAULT_BIND, self.__class__.accept_label_bind)
        box = Gtk.Box(css_classes=["linked"])
        box.append(Button(can_shrink=True, t=Gtk.MenuButton, icon_name="view-more", bindings=[(None, "menu-model", None, "visible", DEFAULT_BIND, bool_bind), (self, "options", None, "menu-model")]))
        box.append(b)
        self.controls.get_child().append(box)
        self.wide.add_bottom_bar(Adw.LayoutSlot.new("controls"))
        self.narrow.add_top_bar(Adw.LayoutSlot.new("controls"))
        self.multi.set_layout_name("narrow")
        self.multi.set_layout_name("wide")
        self.connect("notify::default-filter", self.__class__.default_filter_changed)

    @staticmethod
    def set_icon(image, path): Task.invoke(Info(path=path, do_info=False).set_image_icon, image)

    @staticmethod
    def filter_changed(a, p, self):
        a = self.lookup_action("filter").get_state().unpack()
        if not self.default_filter or self.default_filter.get_name() != a:
            self.default_filter = next((self.filters.get_item(n) for n in range(self.filters.get_n_items()) if self.filters.get_item(n).get_name() == a), None) if self.filters else None

    def default_filter_changed(self, p=None):
        for i in self.view.get_pages():
            i = i.get_child()
            if isinstance(i.get_child(), View):
                while i.get_child().filters.get_n_items() > 1: i.get_child().filters.remove(1)
                if self.default_filter: i.get_child().filters.append(self.default_filter)

    def setup_filters(self, view):
        if self.default_filter: view.filters.append(self.default_filter)

    def handle_load(self, *_):
        if self.initial_file:
            t = self.view.get_selected_page().get_child()
            if hasattr(t.get_child(), "get_items"):
                for i in t.get_child().get_items():
                    if i.path == self.initial_file.get_path(): i.set_selected(True)
        self.default_filter_changed()

    def double_click(self, info):
        if not "folder" in self.operation and info.is_dir: return False
        self.accept()
        return True

    @staticmethod
    def do_replace(d):
        if getattr(d, "dialog"):
            di = d.dialog
            del d.dialog
            di.accept(overwrite=True)

    def accept(self, overwrite=False):
        if "save" in self.operation and not self.entry.get_text(): Toast("Filename required!")
        elif not overwrite and "save" in self.operation and exists(Path(display(self.view.get_selected_page().get_child().path), self.entry.get_text())):
            p = Prompt(heading="Replace File?", callback=self.__class__.do_replace)
            p.dialog = self
            p.present(self)
        elif not "save" in self.operation and not "folder" in self.operation and not self.get_all_selected_items(): Toast("Select a file!")
        else:
            self.do_callback()
            self.set_content(None)
            self.close()

    def do_callback(self):
        c = getattr(self, "callback", None)
        d = getattr(self, "user_data", None)
        if c and d: c(self, None, d)
        elif c: c(self, None)

    def handle_close(self):
        for i in self.view.get_pages():
            if hasattr(i.get_child().get_child(), "cancellable"): i.get_child().get_child().cancellable.cancel()
        if self.cancellable: self.cancellable.disconnect(self.connect_id)
        if self.get_content():
            self.set_content(None)
            self.do_callback()
        self.user_data = self.callback = self.cancellable = None

    def get_result(self):
        if not self.get_content(): raise Exception
        if "save" in self.operation:
            if not self.entry.get_text(): raise Exception
            f = Gio.File.new_for_path(Path(display(self.view.get_selected_page().get_child().path), self.entry.get_text()))
            return (f, "") if "text" in self.operation else f
        r = self.get_all_selected_items()
        if not r:
            if "folder" in self.operation:
                r = [self.view.get_selected_page().get_child().get_child().info]
            else: raise Exception
        if self.multiple:
            f = Gdk.FileList.new_from_list([Gio.File.new_for_path(display(i.path)) for i in r])
            return (f, "") if "text" in self.operation else f
        else:
            f = Gio.File.new_for_path(display(r[0].path))
            return (f, "") if "text" in self.operation else f

    def cancel(c, self):
        if self.get_mapped(): self.close()

    def start(self, parent=None, cancellable=None, callback=None, user_data=None):
        self.user_data = user_data
        self.cancellable = cancellable
        self.callback = callback
        if self.cancellable:
            self.connect_id = self.cancellable.connect(self.__class__.cancel, self)
        if self.initial_file:
            self.initial_folder = self.initial_file.get_parent()
        if self.initial_folder:
            t = None
            for i in self.view.get_pages():
                if i.get_child().path == self.initial_folder.get_path():
                    t = i.get_child()
            if not t:
                t = Tab.create(view=self.view, path=self.initial_folder.get_path())
            self.view.set_selected_page(t.tab)
        if self.extra_menu or self.filters:
            m = {}
            if self.extra_menu:
                m["!a"] = self.extra_menu
            if self.filters:
                f = {}
                for i in self.filters:
                    f[i.get_name()] = f"win.filter::{i.get_name()}"
                m["!b"] = Menu(f)
            if self.extra_menu and self.filters:
                menu = Menu(m)
            elif not self.extra_menu:
                menu = m["!b"]
            elif not self.filters:
                menu = m["!a"]
            self.options = menu
        if self.default_filter: self.lookup_action("filter").set_state(get_variant(self.default_filter.get_name()))
        self.present()
        if self.entry.get_visible(): self.entry.grab_focus()

    def open(self, parent=None, cancellable=None, callback=None, user_data=None):
        self.multiple = False
        self.operation = "open"
        self.entry.set_visible(False)
        self.start(parent=parent, cancellable=cancellable, callback=callback, user_data=user_data)

    def open_multiple(self, parent=None, cancellable=None, callback=None, user_data=None):
        self.multiple = True
        self.operation = "open_multiple"
        self.entry.set_visible(False)
        self.start(parent=parent, cancellable=cancellable, callback=callback, user_data=user_data)

    def open_multiple_text_files(self, parent=None, cancellable=None, callback=None, user_data=None):
        self.multiple = False
        self.operation = "open_multiple_text_files"
        self.entry.set_visible(False)
        self.start(parent=parent, cancellable=cancellable, callback=callback, user_data=user_data)

    def open_text_file(self, parent=None, cancellable=None, callback=None, user_data=None):
        self.multiple = False
        self.operation = "open_text_file"
        self.entry.set_visible(False)
        self.start(parent=parent, cancellable=cancellable, callback=callback, user_data=user_data)

    def save(self, parent=None, cancellable=None, callback=None, user_data=None):
        self.multiple = False
        self.operation = "save"
        self.entry.set_visible(True)
        self.start(parent=parent, cancellable=cancellable, callback=callback, user_data=user_data)

    def save_text_file(self, parent=None, cancellable=None, callback=None, user_data=None):
        self.multiple = False
        self.operation = "save_text_file"
        self.entry.set_visible(True)
        self.start(parent=parent, cancellable=cancellable, callback=callback, user_data=user_data)

    def select_folder(self, parent=None, cancellable=None, callback=None, user_data=None):
        self.multiple = False
        self.operation = "select_folder"
        self.entry.set_visible(False)
        self.start(parent=parent, cancellable=cancellable, callback=callback, user_data=user_data)

    def select_multiple_folders(self, parent=None, cancellable=None, callback=None, user_data=None):
        self.multiple = True
        self.operation = "select_multiple_folders"
        self.entry.set_visible(False)
        self.start(parent=parent, cancellable=cancellable, callback=callback, user_data=user_data)

    def open_finish(self, *_): return self.get_result()
    def open_multiple_finish(self, *_): return self.get_result()
    def open_multiple_text_files_finish(self, *_): return self.get_result()
    def open_text_file_finish(self, *_): return self.get_result()
    def save_finish(self, *_): return self.get_result()
    def save_text_file_finish(self, *_): return self.get_result()
    def select_folder_finish(self, *_): return self.get_result()
    def select_multiple_folders_finish(self, *_): return self.get_result()

    @staticmethod
    def button_accept(b):
        self = b.get_ancestor(FileDialog)
        if self: self.accept()

    @staticmethod
    def button_close(b):
        self = b.get_ancestor(FileDialog)
        if self: self.close()

    @staticmethod
    def accept_label_bind(b, v): return v or "Accept"

HOST_PREFIX = "/run/host/root"
if FLATPAK_ID:
    TRASH = Path(HOST_PREFIX, TRASH)
ROOT = HOST_PREFIX if FLATPAK_ID else SEPARATOR
MAIN_HOME = Path(ROOT, HOME) if FLATPAK_ID else HOME

def display(p):
    if isinstance(p, Gio.File):
        p = p.peek_path()
    return p.split(HOST_PREFIX, 1)[-1] if FLATPAK_ID else p

def open_files(files):
    if not Window.current: Window()
    t = None
    for i in files:
        t = Tab.create(path=i if isinstance(i, str) else i.peek_path())
    if t: t.get_root().view.set_selected_page(t.tab)
    return Window.current.present()

def file_open(a, files, *_): open_files(files)

def activate(a):
    if a.get_active_window(): return a.get_active_window().present()
    else: open_files(ARGS[1:])

def sort_reload(*_):
    for i in View.get_all():
        i.sorter = Info.get_sorter()

INFO = {
    "ID": "io.github.kirukomaru11.Files",
    "Developer": "きるこ丸11号",
    "Comment": "Browse local files",
    "Issue URL": "https://github.com/kirukomaru11/Files/issues",
    "Website": "https://github.com/kirukomaru11/Files",
    "Keywords": ["Browser", "Folder", "Path"],
    "Categories": ["Utility", "FileManager"],
    "Branding": ["#43566f", "#afbdcf"],
    "MimeTypes": ["inode/directory", *Info.archive_types]
}

SHORTCUTS = {
    "Items": {
        "Activate": "space",
        "Move to Trash": "Delete",
        "Delete": "<shift>Delete",
        "Copy": "<primary>c",
        "Cut": "<primary>x",
        "Paste": "<primary>v",
        "Select All": "<primary>a",
        "Properties": "<shift>s",
        "Rename": "<shift>r",
        "Context": "Menu"
    },
    "Tabs": {
        "New": "<primary>t",
        "Close": "<primary>w",
        "Reopen Closed": "<primary><shift>t",
        "Overview": "<primary>o",
        "Reload": "<primary>r F5",
        **Adw.TabView.shortcuts
    },
    "Window": {
        "New": "<primary>n",
        "Fullscreen": "F11",
        "Find": "<primary>f",
        "Stop Find": "Escape",
        "Search": "Return",
        "Background Search": "<shift>Return",
        "Focus Find/Search": "<primary>s",
        "Toggle Names": "<primary>l",
        "Icons Smaller": "<primary>minus",
        "Icons Larger": "<primary>equal",
    },
    "View": handle_scroll.shortcuts
}

APP_CSS = """
.files-window view columnview item-box { border-spacing: 6px; }

.files-window view rubberband { border-radius: 10px; }
.files-window view gridview { border-spacing: 6px; margin: 0px 6px 6px 6px; }
.files-window view gridview child { transition: all 0.2s; padding: 0px; }
.files-window view griditem label { padding: 0px 8px 12px 8px; }
.files-window view griditem > image { margin: 6px 0px 0px 6px; color: var(--window-fg-color); backdrop-filter: blur(10px); padding: 8px; border-radius: 100px; }
.files-window view :selected { background: color-mix(in srgb, var(--window-fg-color) 5%, transparent);  }
.files-window .toolbar-fullscreen view { margin-top: 6px; }
.files-window view griditem image { filter: drop-shadow(0 1px 1px rgba(0, 0, 0, 0.3)); }

.compress list.main.boxed-list > row > entry.password { background: none; min-height: 50px; border-radius: 0px 0px 12px 12px; }
.compress list.main.boxed-list > row > entry.password:focus-within { outline-offset: -1px; outline-width: 2px; }
.compress list.main.boxed-list > row:last-child { padding: 0px; }

.files-window .operations popover { min-width: 360px; }
.files-window .operations operation { padding: 6px; border-spacing: 8px; }
.files-window .operations operation progressbar { padding: 0px 2px;}
.files-window .operations operation box { margin: 0px; border-spacing: 6px; }
.files-window .operations operation > box > image { -gtk-icon-size: 20px; padding: 0px 6px; }
.files-window .operations listview { border-spacing: 8px; padding: 0px; }
.files-window .operations listview row { margin: 0px; padding: 0px; background: color-mix(in srgb, currentColor 5%, transparent); }.files-window .operations scrolledwindow scrollbar { padding: 0px; }

.files-window :drop(active) .highlight { border-color: var(--accent-bg-color); box-shadow: inset 0 0 0 1px var(--accent-bg-color); caret-color: var(--accent-bg-color); }

.files-window icon-size { padding: 0px 14px; }
.files-window icon-size > box { border-spacing: 6px; }

.files-window controls-box { border-spacing: 6px; margin: 6px; }

.files-window .bottom-bar search { margin: 4px 6px 2px 6px; }
.files-window save,
.files-window search { min-height: 34px; }

.files-window search clamp > text {
    border-radius: 10px;
    background: color-mix(in srgb, currentColor 8%, transparent);
    outline: 0 solid transparent;
    outline-offset: 4px;
    transition: outline-color 200ms cubic-bezier(0.25, 0.46, 0.45, 0.94), outline-width 200ms cubic-bezier(0.25, 0.46, 0.45, 0.94), outline-offset 200ms cubic-bezier(0.25, 0.46, 0.45, 0.94);
}
.files-window search.preview { background: none; }
.files-window search viewport > box { border-spacing: 6px; }
.files-window search button { padding: 4px 8px; min-height: 0px; min-width: 0px; border-radius: 8px; }
.files-window save placeholder,
.files-window search placeholder { opacity: var(--dim-opacity); }
.files-window save:focus-within,
.files-window search clamp > text:focus-within { outline-width: 2px; outline-offset: -2px; outline-color: color-mix(in srgb, var(--accent-color) 50%, transparent); }
.files-window find { margin-bottom: 6px; }
.files-window find entry { backdrop-filter: blur(20px) brightness(0.9); background: color-mix(in srgb, var(--window-bg-color) 35%, transparent); min-width: 320px; }
.files-window .toolbar-fullscreen find { margin-top: 6px; }
"""

DATA_INIT = "CREATE TABLE IF NOT EXISTS Settings (Key TEXT PRIMARY KEY NOT NULL, Value TEXT); CREATE TABLE IF NOT EXISTS Tabs (ID INTEGER PRIMARY KEY AUTOINCREMENT, Path TEXT NOT NULL DEFAULT '/'); CREATE TABLE IF NOT EXISTS Icons (Path TEXT PRIMARY KEY NOT NULL, Icon TEXT);"

def main(): App(data=DATA_INIT, file_open=file_open, activate=activate, info=INFO, shortcuts=SHORTCUTS).main(APP_CSS)

if __name__ == "__main__": main()