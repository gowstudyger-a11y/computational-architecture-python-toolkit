import rhinoscriptsyntax as rs
import Rhino
import Rhino.Geometry as rg
import Eto.Drawing as drawing
import Eto.Forms as forms
import scriptcontext as sc
import math


# ============================================================================
# PART 1: CORE GEOMETRY FUNCTIONS (Beginner Level)
# ============================================================================

class EnvelopeGeometry:
    """
    This class handles all geometric operations for the envelope system.
    """

    @staticmethod
    def create_base_footprint(length, width, origin):
        """
        Creates the base rectangular footprint of the building.
        """
        pt1 = rg.Point3d(origin[0], origin[1], origin[2])
        pt2 = rg.Point3d(origin[0] + length, origin[1], origin[2])
        pt3 = rg.Point3d(origin[0] + length, origin[1] + width, origin[2])
        pt4 = rg.Point3d(origin[0], origin[1] + width, origin[2])
        return [pt1, pt2, pt3, pt4]

    @staticmethod
    def create_floor_slab(corners, height):
        """
        Creates a single floor slab at specified height.
        """
        elevated_corners = [rg.Point3d(pt.X, pt.Y, pt.Z + height) for pt in corners]
        elevated_corners.append(elevated_corners[0])
        polyline = rg.Polyline(elevated_corners)
        curve = polyline.ToNurbsCurve()
        
        planar_brep = rg.Brep.CreatePlanarBreps(curve, sc.doc.ModelAbsoluteTolerance)
        if planar_brep:
            guid = sc.doc.Objects.AddBrep(planar_brep[0])
            sc.doc.Views.Redraw()
            return guid
        return None

    @staticmethod
    def create_structural_columns(corners, floor_height, num_floors):
        """
        Creates vertical columns at building corners.
        """
        columns = []
        total_height = floor_height * num_floors
        for corner in corners:
            start_pt = rg.Point3d(corner.X, corner.Y, corner.Z)
            end_pt = rg.Point3d(corner.X, corner.Y, corner.Z + total_height)
            line = rg.Line(start_pt, end_pt)
            guid = sc.doc.Objects.AddLine(line)
            columns.append(guid)
        sc.doc.Views.Redraw()
        return columns


# ============================================================================
# PART 2: ENVELOPE MODULE SYSTEMS (Intermediate Level)
# ============================================================================

class EnvelopeModules:
    """
    Contains three different envelope module types with environmental responsiveness.
    """

    @staticmethod
    def module_type_1_solid_panels(surface_guid, division_u, division_v, offset_distance):
        """
        MODULE TYPE 1: Solid Wooden Panels.
        """
        panels = []
        surface_obj = rs.coercebrep(surface_guid)
        if not surface_obj:
            return panels
        
        surface = surface_obj.Faces[0]
        u_domain = surface.Domain(0)
        v_domain = surface.Domain(1)
        
        u_step = (u_domain.Max - u_domain.Min) / division_u
        v_step = (v_domain.Max - v_domain.Min) / division_v

        for i in range(division_u):
            for j in range(division_v):
                u_start = u_domain.Min + i * u_step
                u_end = u_domain.Min + (i + 1) * u_step
                v_start = v_domain.Min + j * v_step
                v_end = v_domain.Min + (j + 1) * v_step
                
                # Create subsurface
                sub_surface = surface.Trim(
                    rg.Interval(u_start, u_end),
                    rg.Interval(v_start, v_end)
                )
                
                if sub_surface:
                    # Create Brep from surface
                    panel_brep = sub_surface.ToBrep()
                    # Offset the panel
                    offset_breps = rg.Brep.CreateOffsetBrep(
                        panel_brep, 
                        offset_distance, 
                        True, 
                        True, 
                        sc.doc.ModelAbsoluteTolerance
                    )
                    if offset_breps and len(offset_breps) > 0:
                        guid = sc.doc.Objects.AddBrep(offset_breps[0])
                        panels.append(guid)
        
        sc.doc.Views.Redraw()
        return panels

    @staticmethod
    def module_type_2_louvered_system(surface_guid, louver_count, angle, spacing):
        """
        MODULE TYPE 2: Horizontal Louvered System.
        """
        louvers = []
        surface_obj = rs.coercebrep(surface_guid)
        if not surface_obj:
            return louvers
        
        surface = surface_obj.Faces[0]
        v_domain = surface.Domain(1)
        height = v_domain.Max - v_domain.Min
        louver_height = height / louver_count
        
        edges = surface.ToBrep().DuplicateEdgeCurves()
        if not edges or len(edges) < 2:
            return louvers

        for i in range(louver_count):
            v_param = v_domain.Min + (i + 0.5) * louver_height
            
            # Get isocurve at v parameter
            iso_curve = surface.IsoCurve(1, v_param)
            
            if iso_curve:
                louver_depth = spacing
                start_pt = iso_curve.PointAtStart
                end_pt = iso_curve.PointAtEnd
                
                angle_rad = math.radians(angle)
                offset_x = louver_depth * math.cos(angle_rad)
                offset_z = louver_depth * math.sin(angle_rad)

                # Create louver profile
                profile_pts = [
                    start_pt,
                    end_pt,
                    rg.Point3d(end_pt.X + offset_x, end_pt.Y, end_pt.Z + offset_z),
                    rg.Point3d(start_pt.X + offset_x, start_pt.Y, start_pt.Z + offset_z),
                    start_pt
                ]
                
                profile_polyline = rg.Polyline(profile_pts)
                profile_curve = profile_polyline.ToNurbsCurve()
                
                planar_brep = rg.Brep.CreatePlanarBreps(
                    profile_curve, 
                    sc.doc.ModelAbsoluteTolerance
                )
                
                if planar_brep and len(planar_brep) > 0:
                    guid = sc.doc.Objects.AddBrep(planar_brep[0])
                    louvers.append(guid)
        
        sc.doc.Views.Redraw()
        return louvers

    @staticmethod
    def module_type_3_cellular_pattern(surface_guid, cell_size, depth_variation):
        """
        MODULE TYPE 3: Cellular/Hexagonal Pattern.
        """
        cells = []
        surface_obj = rs.coercebrep(surface_guid)
        if not surface_obj:
            return cells
        
        surface = surface_obj.Faces[0]
        u_domain = surface.Domain(0)
        v_domain = surface.Domain(1)

        rows = int((v_domain.Max - v_domain.Min) / cell_size) + 1
        cols = int((u_domain.Max - u_domain.Min) / cell_size) + 1

        for row in range(rows):
            for col in range(cols):
                u = u_domain.Min + col * cell_size
                v = v_domain.Min + row * cell_size
                
                # Offset every other row
                if row % 2 == 1:
                    u += cell_size * 0.5
                
                if u <= u_domain.Max and v <= v_domain.Max:
                    cell_center = surface.PointAt(u, v)
                    
                    if cell_center:
                        hex_points = []
                        for ang in range(0, 360, 60):
                            angle_rad = math.radians(ang)
                            x_offset = cell_size * 0.5 * math.cos(angle_rad)
                            y_offset = cell_size * 0.5 * math.sin(angle_rad)
                            pt = rg.Point3d(
                                cell_center.X + x_offset,
                                cell_center.Y + y_offset,
                                cell_center.Z
                            )
                            hex_points.append(pt)
                        hex_points.append(hex_points[0])
                        
                        hex_polyline = rg.Polyline(hex_points)
                        hex_curve = hex_polyline.ToNurbsCurve()
                        
                        cell_brep = rg.Brep.CreatePlanarBreps(
                            hex_curve, 
                            sc.doc.ModelAbsoluteTolerance
                        )
                        
                        if cell_brep and len(cell_brep) > 0:
                            depth = depth_variation * (
                                0.5 + 0.5 * math.sin(col * 0.5) * math.cos(row * 0.5)
                            )
                            
                            offset_breps = rg.Brep.CreateOffsetBrep(
                                cell_brep[0], 
                                depth, 
                                True, 
                                True, 
                                sc.doc.ModelAbsoluteTolerance
                            )
                            
                            if offset_breps and len(offset_breps) > 0:
                                guid = sc.doc.Objects.AddBrep(offset_breps[0])
                                cells.append(guid)
        
        sc.doc.Views.Redraw()
        return cells


# ============================================================================
# PART 3: OPENINGS SYSTEM (Windows & Doors)
# ============================================================================

class OpeningsSystem:
    """
    Handles creation of windows and doors with parametric control.
    """

    @staticmethod
    def create_window(wall_surface_guid, position_u, position_v, width, height):
        """
        Creates a window opening on a wall surface.
        """
        surface_obj = rs.coercebrep(wall_surface_guid)
        if not surface_obj:
            return None
        
        surface = surface_obj.Faces[0]
        u_domain = surface.Domain(0)
        v_domain = surface.Domain(1)

        u = u_domain.Min + position_u * (u_domain.Max - u_domain.Min)
        v = v_domain.Min + position_v * (v_domain.Max - v_domain.Min)

        center_pt = surface.PointAt(u, v)
        normal = surface.NormalAt(u, v)

        if center_pt:
            half_width = width / 2
            half_height = height / 2
            
            corners = [
                rg.Point3d(center_pt.X - half_width, center_pt.Y, center_pt.Z - half_height),
                rg.Point3d(center_pt.X + half_width, center_pt.Y, center_pt.Z - half_height),
                rg.Point3d(center_pt.X + half_width, center_pt.Y, center_pt.Z + half_height),
                rg.Point3d(center_pt.X - half_width, center_pt.Y, center_pt.Z + half_height),
                rg.Point3d(center_pt.X - half_width, center_pt.Y, center_pt.Z - half_height)
            ]
            
            window_polyline = rg.Polyline(corners)
            window_curve = window_polyline.ToNurbsCurve()
            window_brep = rg.Brep.CreatePlanarBreps(
                window_curve, 
                sc.doc.ModelAbsoluteTolerance
            )
            
            if window_brep and len(window_brep) > 0:
                guid = sc.doc.Objects.AddBrep(window_brep[0])
                sc.doc.Views.Redraw()
                return guid
        return None

    @staticmethod
    def create_door(wall_surface_guid, position_u, width, height):
        """
        Creates a door opening at ground level.
        """
        surface_obj = rs.coercebrep(wall_surface_guid)
        if not surface_obj:
            return None
        
        surface = surface_obj.Faces[0]
        u_domain = surface.Domain(0)
        v_domain = surface.Domain(1)

        u = u_domain.Min + position_u * (u_domain.Max - u_domain.Min)
        v = v_domain.Min

        base_pt = surface.PointAt(u, v)

        if base_pt:
            half_width = width / 2
            corners = [
                rg.Point3d(base_pt.X - half_width, base_pt.Y, base_pt.Z),
                rg.Point3d(base_pt.X + half_width, base_pt.Y, base_pt.Z),
                rg.Point3d(base_pt.X + half_width, base_pt.Y, base_pt.Z + height),
                rg.Point3d(base_pt.X - half_width, base_pt.Y, base_pt.Z + height),
                rg.Point3d(base_pt.X - half_width, base_pt.Y, base_pt.Z)
            ]
            
            door_polyline = rg.Polyline(corners)
            door_curve = door_polyline.ToNurbsCurve()
            door_brep = rg.Brep.CreatePlanarBreps(
                door_curve, 
                sc.doc.ModelAbsoluteTolerance
            )
            
            if door_brep and len(door_brep) > 0:
                guid = sc.doc.Objects.AddBrep(door_brep[0])
                sc.doc.Views.Redraw()
                return guid
        return None


# ============================================================================
# PART 4: BUILDING GENERATOR (Advanced Level)
# ============================================================================

class BuildingGenerator:
    """
    Main class that orchestrates the complete building generation.
    """

    def __init__(self):
        self.length = 10.0
        self.width = 8.0
        self.floor_height = 3.0
        self.num_floors = 2

        self.module_type = 1
        self.panel_divisions = 5
        self.louver_count = 8
        self.louver_angle = 30
        self.cell_size = 1.0

        self.window_width = 1.5
        self.window_height = 1.8
        self.door_width = 1.0
        self.door_height = 2.1

        self.generated_objects = []

    def clear_previous_geometry(self):
        if self.generated_objects:
            for guid in self.generated_objects:
                if rs.IsObject(guid):
                    rs.DeleteObject(guid)
            self.generated_objects = []
        sc.doc.Views.Redraw()

    def generate_complete_building(self):
        self.clear_previous_geometry()

        origin = (0, 0, 0)
        corners = EnvelopeGeometry.create_base_footprint(
            self.length, self.width, origin
        )

        # Create floor slabs
        for floor in range(self.num_floors + 1):
            height = floor * self.floor_height
            slab = EnvelopeGeometry.create_floor_slab(corners, height)
            if slab:
                self.generated_objects.append(slab)

        # Create columns
        columns = EnvelopeGeometry.create_structural_columns(
            corners, self.floor_height, self.num_floors
        )
        self.generated_objects.extend(columns)

        # Create walls
        total_height = self.floor_height * self.num_floors
        walls = self.create_wall_surfaces(corners, total_height)

        # Apply envelope modules
        for wall in walls:
            modules = self.apply_envelope_modules(wall)
            self.generated_objects.extend(modules)

        # Add openings
        self.add_openings(walls)
        
        # Apply materials
        self.apply_materials()
        
        rs.ZoomExtents()
        sc.doc.Views.Redraw()
        return True

    def create_wall_surfaces(self, corners, height):
        """Creates wall surfaces between corners"""
        walls = []
        for i in range(len(corners)):
            next_i = (i + 1) % len(corners)
            pt1 = corners[i]
            pt2 = corners[next_i]
            pt3 = rg.Point3d(pt2.X, pt2.Y, pt2.Z + height)
            pt4 = rg.Point3d(pt1.X, pt1.Y, pt1.Z + height)
            
            wall_corners = [pt1, pt2, pt3, pt4, pt1]
            wall_polyline = rg.Polyline(wall_corners)
            wall_curve = wall_polyline.ToNurbsCurve()
            
            wall_brep = rg.Brep.CreatePlanarBreps(
                wall_curve, 
                sc.doc.ModelAbsoluteTolerance
            )
            
            if wall_brep and len(wall_brep) > 0:
                guid = sc.doc.Objects.AddBrep(wall_brep[0])
                walls.append(guid)
        
        sc.doc.Views.Redraw()
        return walls

    def apply_envelope_modules(self, wall_surface):
        """Applies selected envelope module type to wall"""
        modules = []
        if self.module_type == 1:
            modules = EnvelopeModules.module_type_1_solid_panels(
                wall_surface,
                self.panel_divisions,
                self.panel_divisions,
                0.2
            )
        elif self.module_type == 2:
            modules = EnvelopeModules.module_type_2_louvered_system(
                wall_surface,
                self.louver_count,
                self.louver_angle,
                0.3
            )
        elif self.module_type == 3:
            modules = EnvelopeModules.module_type_3_cellular_pattern(
                wall_surface,
                self.cell_size,
                0.5
            )
        return modules

    def add_openings(self, walls):
        """Adds windows and doors to walls"""
        if len(walls) < 2:
            return

        # Add door to first wall
        door = OpeningsSystem.create_door(
            walls[0], 0.5, self.door_width, self.door_height
        )
        if door:
            self.generated_objects.append(door)

        # Add windows to other walls
        for wall in walls[1:]:
            window = OpeningsSystem.create_window(
                wall, 0.3, 0.5, self.window_width, self.window_height
            )
            if window:
                self.generated_objects.append(window)
            
            window2 = OpeningsSystem.create_window(
                wall, 0.7, 0.5, self.window_width, self.window_height
            )
            if window2:
                self.generated_objects.append(window2)

    def apply_materials(self):
        """Applies colors to generated objects"""
        color = drawing.Color.FromArgb(200, 180, 150)
        for obj in self.generated_objects:
            if rs.IsObject(obj):
                rs.ObjectColor(obj, (200, 180, 150))
        sc.doc.Views.Redraw()


# ============================================================================
# PART 5: ETO FORMS UI (Advanced Level)
# ============================================================================

class EnvelopeConfiguratorDialog(forms.Dialog):
    """
    Main UI dialog using Eto Forms for parametric control.
    """

    def __init__(self):
        super(EnvelopeConfiguratorDialog, self).__init__()
        self.generator = BuildingGenerator()
        self.Title = "Parametric Envelope Configurator"
        self.Padding = drawing.Padding(10)
        self.Resizable = True
        self.MinimumSize = drawing.Size(400, 600)
        self.Content = self.create_layout()

    def create_layout(self):
        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(5, 5)

        # SECTION 1: BUILDING DIMENSIONS
        bold_font = forms.Font(forms.SystemFont.Bold, 10)
        layout.AddRow(forms.Label(Text="BUILDING DIMENSIONS", Font=bold_font))
        layout.AddRow(None)

        self.length_slider = forms.Slider()
        self.length_slider.MinValue = 5
        self.length_slider.MaxValue = 20
        self.length_slider.Value = int(self.generator.length)
        self.length_label = forms.Label(Text="Length: {} m".format(self.generator.length))
        self.length_slider.ValueChanged += self.on_length_changed

        layout.AddRow(forms.Label(Text="Building Length:"))
        layout.AddRow(self.length_slider)
        layout.AddRow(self.length_label)

        self.width_slider = forms.Slider()
        self.width_slider.MinValue = 5
        self.width_slider.MaxValue = 20
        self.width_slider.Value = int(self.generator.width)
        self.width_label = forms.Label(Text="Width: {} m".format(self.generator.width))
        self.width_slider.ValueChanged += self.on_width_changed

        layout.AddRow(forms.Label(Text="Building Width:"))
        layout.AddRow(self.width_slider)
        layout.AddRow(self.width_label)

        self.floor_height_slider = forms.Slider()
        self.floor_height_slider.MinValue = 25
        self.floor_height_slider.MaxValue = 40
        self.floor_height_slider.Value = int(self.generator.floor_height * 10)
        self.floor_height_label = forms.Label(Text="Floor Height: {} m".format(self.generator.floor_height))
        self.floor_height_slider.ValueChanged += self.on_floor_height_changed

        layout.AddRow(forms.Label(Text="Floor Height:"))
        layout.AddRow(self.floor_height_slider)
        layout.AddRow(self.floor_height_label)

        self.num_floors_dropdown = forms.DropDown()
        self.num_floors_dropdown.DataStore = ["1 Floor", "2 Floors", "3 Floors"]
        self.num_floors_dropdown.SelectedIndex = self.generator.num_floors - 1
        self.num_floors_dropdown.SelectedIndexChanged += self.on_num_floors_changed

        layout.AddRow(forms.Label(Text="Number of Floors:"))
        layout.AddRow(self.num_floors_dropdown)
        layout.AddRow(None)

        # SECTION 2: ENVELOPE MODULE TYPE
        layout.AddRow(forms.Label(Text="ENVELOPE MODULE TYPE", Font=bold_font))
        layout.AddRow(None)

        self.module_radio = forms.RadioButtonList()
        self.module_radio.DataStore = [
            "Type 1: Solid Wooden Panels",
            "Type 2: Louvered System (Solar Shading)",
            "Type 3: Cellular Pattern (Light Diffusion)"
        ]
        self.module_radio.SelectedIndex = 0
        self.module_radio.SelectedIndexChanged += self.on_module_type_changed

        layout.AddRow(self.module_radio)
        layout.AddRow(None)

        self.module_params_layout = forms.DynamicLayout()
        self.update_module_parameters()
        layout.AddRow(self.module_params_layout)
        layout.AddRow(None)

        # SECTION 3: OPENINGS
        layout.AddRow(forms.Label(Text="OPENINGS (Windows & Doors)", Font=bold_font))
        layout.AddRow(None)

        self.window_width_slider = forms.Slider()
        self.window_width_slider.MinValue = 10
        self.window_width_slider.MaxValue = 30
        self.window_width_slider.Value = int(self.generator.window_width * 10)
        self.window_width_label = forms.Label(Text="Window Width: {} m".format(self.generator.window_width))
        self.window_width_slider.ValueChanged += self.on_window_width_changed

        layout.AddRow(forms.Label(Text="Window Width:"))
        layout.AddRow(self.window_width_slider)
        layout.AddRow(self.window_width_label)
        layout.AddRow(None)

        # SECTION 4: ACTION BUTTONS
        generate_button = forms.Button(Text="Generate Building")
        generate_button.Click += self.on_generate_clicked

        reset_button = forms.Button(Text="Reset Parameters")
        reset_button.Click += self.on_reset_clicked

        close_button = forms.Button(Text="Close")
        close_button.Click += self.on_close_clicked

        button_layout = forms.DynamicLayout()
        button_layout.AddRow(generate_button, reset_button, close_button)

        layout.AddRow(None)
        layout.AddRow(button_layout)

        return layout

    def update_module_parameters(self):
        """Updates UI based on selected module type"""
        self.module_params_layout.Clear()
        module_type = self.module_radio.SelectedIndex + 1

        if module_type == 1:
            # Solid Panels parameters
            self.panel_div_slider = forms.Slider()
            self.panel_div_slider.MinValue = 3
            self.panel_div_slider.MaxValue = 10
            self.panel_div_slider.Value = self.generator.panel_divisions
            self.panel_div_label = forms.Label(Text="Divisions: {}".format(self.generator.panel_divisions))
            self.panel_div_slider.ValueChanged += self.on_panel_div_changed

            self.module_params_layout.AddRow(forms.Label(Text="Panel Divisions:"))
            self.module_params_layout.AddRow(self.panel_div_slider)
            self.module_params_layout.AddRow(self.panel_div_label)

        elif module_type == 2:
            # Louvered System parameters
            self.louver_count_slider = forms.Slider()
            self.louver_count_slider.MinValue = 5
            self.louver_count_slider.MaxValue = 20
            self.louver_count_slider.Value = self.generator.louver_count
            self.louver_count_label = forms.Label(Text="Louver Count: {}".format(self.generator.louver_count))
            self.louver_count_slider.ValueChanged += self.on_louver_count_changed

            self.louver_angle_slider = forms.Slider()
            self.louver_angle_slider.MinValue = 0
            self.louver_angle_slider.MaxValue = 60
            self.louver_angle_slider.Value = self.generator.louver_angle
            self.louver_angle_label = forms.Label(Text="Louver Angle: {}°".format(self.generator.louver_angle))
            self.louver_angle_slider.ValueChanged += self.on_louver_angle_changed

            self.module_params_layout.AddRow(forms.Label(Text="Louver Count:"))
            self.module_params_layout.AddRow(self.louver_count_slider)
            self.module_params_layout.AddRow(self.louver_count_label)

            self.module_params_layout.AddRow(forms.Label(Text="Louver Angle:"))
            self.module_params_layout.AddRow(self.louver_angle_slider)
            self.module_params_layout.AddRow(self.louver_angle_label)

        elif module_type == 3:
            # Cellular Pattern parameters
            self.setup_cellular_params()

    def setup_cellular_params(self):
        """Sets up cellular pattern parameters"""
        self.cell_size_slider = forms.Slider()
        self.cell_size_slider.MinValue = 5
        self.cell_size_slider.MaxValue = 20
        self.cell_size_slider.Value = int(self.generator.cell_size * 10)
        self.cell_size_label = forms.Label(Text="Cell Size: {} m".format(self.generator.cell_size))
        self.cell_size_slider.ValueChanged += self.on_cell_size_changed

        self.module_params_layout.AddRow(forms.Label(Text="Cell Size:"))
        self.module_params_layout.AddRow(self.cell_size_slider)
        self.module_params_layout.AddRow(self.cell_size_label)

    # ========================================================================
    # EVENT HANDLERS - COMPLETE IMPLEMENTATION
    # ========================================================================

    def on_length_changed(self, sender, e):
        self.generator.length = float(self.length_slider.Value)
        self.length_label.Text = "Length: {} m".format(self.generator.length)

    def on_width_changed(self, sender, e):
        self.generator.width = float(self.width_slider.Value)
        self.width_label.Text = "Width: {} m".format(self.generator.width)

    def on_floor_height_changed(self, sender, e):
        self.generator.floor_height = self.floor_height_slider.Value / 10.0
        self.floor_height_label.Text = "Floor Height: {} m".format(self.generator.floor_height)

    def on_num_floors_changed(self, sender, e):
        self.generator.num_floors = self.num_floors_dropdown.SelectedIndex + 1

    def on_module_type_changed(self, sender, e):
        self.generator.module_type = self.module_radio.SelectedIndex + 1
        self.update_module_parameters()

    def on_panel_div_changed(self, sender, e):
        self.generator.panel_divisions = int(self.panel_div_slider.Value)
        self.panel_div_label.Text = "Divisions: {}".format(self.generator.panel_divisions)

    def on_louver_count_changed(self, sender, e):
        self.generator.louver_count = int(self.louver_count_slider.Value)
        self.louver_count_label.Text = "Louver Count: {}".format(self.generator.louver_count)

    def on_louver_angle_changed(self, sender, e):
        self.generator.louver_angle = int(self.louver_angle_slider.Value)
        self.louver_angle_label.Text = "Louver Angle: {}°".format(self.generator.louver_angle)

    def on_cell_size_changed(self, sender, e):
        self.generator.cell_size = self.cell_size_slider.Value / 10.0
        self.cell_size_label.Text = "Cell Size: {} m".format(self.generator.cell_size)

    def on_window_width_changed(self, sender, e):
        self.generator.window_width = self.window_width_slider.Value / 10.0
        self.window_width_label.Text = "Window Width: {} m".format(self.generator.window_width)

    def on_generate_clicked(self, sender, e):
        """Generate button clicked - creates the building"""
        try:
            success = self.generator.generate_complete_building()
            if success:
                forms.MessageBox.Show("Building generated successfully!", "Success")
        except Exception as ex:
            forms.MessageBox.Show("Error generating building: {}".format(str(ex)), "Error")

    def on_reset_clicked(self, sender, e):
        """Reset button clicked - resets all parameters to default"""
        self.generator = BuildingGenerator()
        
        # Reset all sliders and controls
        self.length_slider.Value = int(self.generator.length)
        self.width_slider.Value = int(self.generator.width)
        self.floor_height_slider.Value = int(self.generator.floor_height * 10)
        self.num_floors_dropdown.SelectedIndex = self.generator.num_floors - 1
        self.module_radio.SelectedIndex = 0
        self.window_width_slider.Value = int(self.generator.window_width * 10)
        
        # Update all labels
        self.length_label.Text = "Length: {} m".format(self.generator.length)
        self.width_label.Text = "Width: {} m".format(self.generator.width)
        self.floor_height_label.Text = "Floor Height: {} m".format(self.generator.floor_height)
        self.window_width_label.Text = "Window Width: {} m".format(self.generator.window_width)
        
        self.update_module_parameters()
        
        forms.MessageBox.Show("Parameters reset to default values.", "Reset")

    def on_close_clicked(self, sender, e):
        """Close button clicked - closes the dialog"""
        self.Close()


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main function to launch the dialog"""
    dialog = EnvelopeConfiguratorDialog()
    dialog.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)

# Run the main function
if __name__ == "__main__":
    main()