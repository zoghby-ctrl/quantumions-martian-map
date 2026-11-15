using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Text;

namespace MarswalkVideo
{
    public static class Maker
    {
        const int W = 1280, H = 720, FPS = 1, FRAMES = 60;
        static readonly Color Bg = Color.FromArgb(16, 23, 22);
        static readonly Color Panel = Color.FromArgb(24, 34, 31);
        static readonly Color Line = Color.FromArgb(51, 66, 59);
        static readonly Color White = Color.FromArgb(238, 241, 232);
        static readonly Color Muted = Color.FromArgb(153, 169, 159);
        static readonly Color Green = Color.FromArgb(200, 241, 105);
        static readonly Color Blue = Color.FromArgb(114, 185, 247);
        static readonly Color Orange = Color.FromArgb(255, 183, 107);
        static readonly Color Red = Color.FromArgb(238, 121, 96);
        static readonly int[][] Obstacles = new int[][] { new[]{10,10}, new[]{9,10}, new[]{10,9}, new[]{11,10}, new[]{10,11} };
        static readonly int[][] Classic = new int[][] { new[]{13,5},new[]{12,6},new[]{11,7},new[]{10,8},new[]{9,8},new[]{8,9},new[]{8,10},new[]{8,11},new[]{8,12},new[]{8,13} };
        static readonly int[][] Quantum = new int[][] { new[]{13,5},new[]{13,6},new[]{13,7},new[]{13,8},new[]{13,9},new[]{13,10},new[]{12,11},new[]{11,12},new[]{10,13},new[]{9,13},new[]{8,13} };

        static void Text(Graphics g, string value, float x, float y, float size, Color color, bool bold = false, string family = "Arial")
        {
            using (var font = new Font(family, size, bold ? FontStyle.Bold : FontStyle.Regular, GraphicsUnit.Pixel))
            using (var brush = new SolidBrush(color))
                g.DrawString(value, font, brush, x, y);
        }

        static void Wrap(Graphics g, string value, RectangleF rect, float size, Color color, bool bold = false)
        {
            using (var font = new Font("Arial", size, bold ? FontStyle.Bold : FontStyle.Regular, GraphicsUnit.Pixel))
            using (var brush = new SolidBrush(color))
                g.DrawString(value, font, brush, rect);
        }

        static void Box(Graphics g, float x, float y, float w, float h, Color fill, Color border)
        {
            using (var b = new SolidBrush(fill)) g.FillRectangle(b, x, y, w, h);
            using (var p = new Pen(border, 1)) g.DrawRectangle(p, x, y, w, h);
        }

        static void Base(Graphics g, int sec, string section, string title, string subtitle)
        {
            g.Clear(Bg);
            using (var b = new SolidBrush(Color.FromArgb(21, 30, 27))) g.FillRectangle(b, 0, 0, W, 58);
            using (var p = new Pen(Line, 1)) g.DrawLine(p, 0, 58, W, 58);
            Box(g, 54, 13, 30, 30, Bg, Green);
            Text(g, "M", 62, 16, 21, Green, true, "Arial");
            Text(g, "MARSWALK", 98, 14, 15, White, true);
            Text(g, "FIELD ROUTE LAB", 98, 34, 9, Muted, false, "Consolas");
            Text(g, "JEZERO | SYNTHETIC TERRAIN", 935, 23, 11, Muted, false, "Consolas");
            Text(g, section.ToUpperInvariant(), 58, 84, 11, Green, false, "Consolas");
            Text(g, title, 58, 112, 39, White, true);
            Wrap(g, subtitle, new RectangleF(60, 166, 1040, 43), 16, Muted);
            using (var p = new Pen(Line, 1)) g.DrawLine(p, 58, 674, 1222, 674);
            Text(g, "VISUAL BACKUP | CURATED ILLUSTRATION | NOT LIVE SOLVER OUTPUT", 58, 685, 10, Color.FromArgb(227, 199, 127), false, "Consolas");
            Text(g, "MARSWALK", 1120, 685, 10, Muted, false, "Consolas");
            using (var b = new SolidBrush(Color.FromArgb(42, 55, 49))) g.FillRectangle(b, 58, 660, 1164, 3);
            using (var b = new SolidBrush(Green)) g.FillRectangle(b, 58, 660, 1164f * (sec + 1) / FRAMES, 3);
        }

        static void DrawRouteMap(Graphics g, float x, float y, float cell)
        {
            using (var b = new SolidBrush(Color.FromArgb(14, 25, 23))) g.FillRectangle(b, x - 12, y - 12, cell * 20 + 24, cell * 20 + 24);
            for (int r = 0; r < 20; r++) for (int c = 0; c < 20; c++)
            {
                Color fill = ((r + c) % 3 == 0) ? Color.FromArgb(48, 68, 57) : Color.FromArgb(38, 56, 49);
                if (Math.Abs(r - 10) <= 2 && Math.Abs(c - 10) <= 3) fill = Color.FromArgb(90, 70, 47);
                if (Math.Abs(r - 10) <= 1 && Math.Abs(c - 10) <= 1) fill = Color.FromArgb(116, 75, 48);
                foreach (var obstacle in Obstacles) if (obstacle[0] == r && obstacle[1] == c) fill = Color.FromArgb(153, 72, 57);
                using (var b = new SolidBrush(fill)) g.FillRectangle(b, x + c * cell, y + r * cell, cell - 2, cell - 2);
                using (var p = new Pen(Color.FromArgb(35, 122, 143, 126), 1)) g.DrawRectangle(p, x + c * cell, y + r * cell, cell - 2, cell - 2);
            }
            DrawPath(g, Classic, x, y, cell, Blue, false);
            DrawPath(g, Quantum, x, y, cell, Orange, true);
            using (var b = new SolidBrush(Blue)) g.FillEllipse(b, x + 5 * cell + cell / 2 - 7, y + 13 * cell + cell / 2 - 7, 14, 14);
            using (var b = new SolidBrush(Orange)) g.FillRectangle(b, x + 13 * cell + cell / 2 - 6, y + 8 * cell + cell / 2 - 6, 12, 12);
        }

        static void DrawPath(Graphics g, int[][] path, float x, float y, float cell, Color color, bool dashed)
        {
            using (var pen = new Pen(Color.FromArgb(24, 28, 27), 9))
            using (var route = new Pen(color, 4))
            {
                pen.LineJoin = LineJoin.Round; route.LineJoin = LineJoin.Round; route.StartCap = LineCap.Round; route.EndCap = LineCap.Round;
                if (dashed) route.DashPattern = new float[] { 3, 2 };
                for (int i = 0; i < path.Length - 1; i++)
                {
                    float x1 = x + path[i][1] * cell + cell / 2, y1 = y + path[i][0] * cell + cell / 2;
                    float x2 = x + path[i + 1][1] * cell + cell / 2, y2 = y + path[i + 1][0] * cell + cell / 2;
                    g.DrawLine(pen, x1, y1, x2, y2); g.DrawLine(route, x1, y1, x2, y2);
                }
            }
        }

        static void DrawSlide(Graphics g, int frame)
        {
            int scene = frame / 10;
            if (scene == 0)
            {
                Base(g, frame, "Jezero / rover route comparison", "A traverse, seen two ways.", "Lock one signature path before the presentation. Keep the live demo focused on one terrain window and one set of weights.");
                Box(g, 60, 238, 1160, 330, Panel, Line);
                Text(g, "GOLDEN DEMO MARSWALK", 92, 268, 12, Green, false, "Consolas");
                Text(g, "Western delta deposit", 92, 321, 31, White, true);
                Text(g, "18.44 N   77.45 E", 94, 366, 18, Blue, false, "Consolas");
                using (var pen = new Pen(Green, 2)) { pen.EndCap = LineCap.ArrowAnchor; g.DrawLine(pen, 520, 385, 720, 385); }
                Text(g, "Jezero crater rim", 795, 321, 31, White, true);
                Text(g, "18.52 N   77.62 E", 797, 366, 18, Orange, false, "Consolas");
                Text(g, "Load Demo Marswalk / fill endpoints / run both solvers", 94, 477, 17, Muted);
                Text(g, "A repeatable route makes the visual comparison easy to explain.", 94, 520, 14, Muted);
            }
            else if (scene == 1)
            {
                Base(g, frame, "01 / golden route", "Start with the same inputs.", "The demo preset fixes the endpoints and hazard balance so the comparison is repeatable on stage.");
                Box(g, 60, 237, 545, 348, Panel, Line); Box(g, 635, 237, 585, 348, Panel, Line);
                Text(g, "START", 88, 266, 11, Muted, false, "Consolas"); Text(g, "18.44 N", 88, 297, 25, White, true); Text(g, "77.45 E", 88, 337, 20, Blue, false, "Consolas");
                Text(g, "DESTINATION", 88, 395, 11, Muted, false, "Consolas"); Text(g, "18.52 N", 88, 426, 25, White, true); Text(g, "77.62 E", 88, 466, 20, Orange, false, "Consolas");
                Text(g, "TERRAIN PRIORITIES", 666, 266, 11, Green, false, "Consolas");
                Text(g, "Slope & rollover", 666, 309, 15, White); Text(g, "35%", 1128, 309, 15, Green, false, "Consolas");
                Box(g, 666, 339, 490, 7, Color.FromArgb(49, 64, 55), Color.FromArgb(49, 64, 55)); Box(g, 666, 339, 172, 7, Green, Green);
                Text(g, "Radiation exposure", 666, 382, 15, White); Text(g, "45%", 1128, 382, 15, Green, false, "Consolas");
                Box(g, 666, 412, 490, 7, Color.FromArgb(49, 64, 55), Color.FromArgb(49, 64, 55)); Box(g, 666, 412, 220, 7, Green, Green);
                Text(g, "Crater proximity receives the remaining 20%.", 666, 451, 13, Muted);
                Box(g, 666, 500, 490, 49, Green, Green); Text(g, "LOAD DEMO MARSWALK  /  RUN ROUTES", 684, 514, 14, Bg, true, "Consolas");
            }
            else if (scene == 2)
            {
                Base(g, frame, "02 / route overlay", "A* and QAOA take different lines.", "The curated preview routes around an impassable crater and highlights a hazardous scarp corridor.");
                DrawRouteMap(g, 120, 236, 20);
                Text(g, "SYNTHETIC HAZARD GRID", 590, 248, 11, Green, false, "Consolas");
                Text(g, "A* / full-grid optimum", 590, 300, 18, Blue, true); Text(g, "Shorter traverse through a moderate-risk corridor.", 590, 328, 15, Muted);
                Text(g, "QAOA / waypoint subgraph", 590, 393, 18, Orange, true); Text(g, "A sampled route that skirts the marked hazard zone.", 590, 421, 15, Muted);
                using (var b = new SolidBrush(Color.FromArgb(153, 72, 57))) g.FillRectangle(b, 590, 476, 18, 18); Text(g, "Impassable crater cells", 622, 477, 13, Muted);
                using (var b = new SolidBrush(Color.FromArgb(96, 74, 49))) g.FillRectangle(b, 590, 512, 18, 18); Text(g, "Elevated hazard corridor", 622, 513, 13, Muted);
                Text(g, "Both paths use legal adjacent moves.", 590, 558, 13, White);
            }
            else if (scene == 3)
            {
                Base(g, frame, "03 / side-by-side", "Show what changed - and what did not.", "These figures belong to the curated visual fallback, not a live run. Live results are recomputed from the API route geometries.");
                Metric(g, 60, 251, 352, "CLASSICAL A*", "22.84", "weighted route cost", "Distance     10.7 cells", "Hazard       1.81", Blue);
                Metric(g, 464, 251, 352, "QAOA WAYPOINT", "25.31", "weighted route cost", "Distance     11.2 cells", "Hazard       1.29", Orange);
                Metric(g, 868, 251, 352, "ROUTE DELTA", "+10.8%", "illustrative QAOA cost vs A*", "QAOA steps  10", "Full-grid optimum  A*", Green);
                Box(g, 60, 505, 1160, 70, Color.FromArgb(43, 43, 29), Color.FromArgb(117, 95, 51));
                Wrap(g, "Read the tradeoff as a route-choice illustration. QAOA may return a feasible route that costs more; the comparison does not claim the quantum solver is faster or better.", new RectangleF(82, 520, 1110, 42), 15, Color.FromArgb(241, 215, 153));
            }
            else if (scene == 4)
            {
                Base(g, frame, "04 / edge cases", "Make failure modes readable.", "The controls should tell the operator what needs changing instead of leaving a blank map or a server traceback.");
                Edge(g, 60, 245, "01", "Click inside a crater", "Keep the endpoint where it is. Explain that the crater cell is impassable.", Red);
                Edge(g, 650, 245, "02", "Outside the map window", "Show the Jezero latitude and longitude limits next to the warning.", Orange);
                Edge(g, 60, 414, "03", "Weights total over 100%", "Flag the sum and ask for one slider to be lowered. Zero and 100% remain valid edges.", Green);
                Edge(g, 650, 414, "04", "Backend is slow or offline", "Load the labeled visual preview so the map remains explainable.", Blue);
            }
            else
            {
                Base(g, frame, "05 / judge answer", "QAOA explores a smaller route-choice problem.", "A concise explanation: QAOA is a heuristic candidate search over a waypoint QUBO - not a speedup claim.");
                Box(g, 60, 245, 340, 188, Panel, Line); Box(g, 470, 245, 340, 188, Panel, Line); Box(g, 880, 245, 340, 188, Panel, Line);
                Text(g, "A*", 88, 276, 29, Blue, true); Wrap(g, "Searches the full cell grid and gives the lowest-cost legal route for these weights.", new RectangleF(88, 327, 275, 72), 16, Muted);
                Text(g, "WAYPOINT QUBO", 498, 276, 18, Orange, true); Wrap(g, "Binary arc choices minimize route cost. Flow penalties enforce one source-to-goal path.", new RectangleF(498, 327, 275, 72), 16, Muted);
                Text(g, "QAOA", 908, 276, 29, Green, true); Wrap(g, "Samples candidate bitstrings. Keep the best valid path, expand it to terrain cells, and rescore it.", new RectangleF(908, 327, 275, 72), 16, Muted);
                Box(g, 60, 474, 1160, 75, Color.FromArgb(25, 39, 32), Color.FromArgb(62, 91, 66));
                Text(g, "WHAT WE CLAIM", 86, 490, 10, Green, false, "Consolas");
                Wrap(g, "A transparent comparison of two route solvers under the same synthetic terrain costs. The waypoint route may be longer; we do not claim quantum advantage.", new RectangleF(86, 511, 1100, 30), 14, White);
            }
        }

        static void Metric(Graphics g, int x, int y, int w, string title, string number, string unit, string a, string b, Color color)
        {
            Box(g, x, y, w, 220, Panel, Line);
            Text(g, title, x + 22, y + 20, 11, Muted, false, "Consolas");
            Text(g, number, x + 22, y + 60, 39, color, true);
            Text(g, unit, x + 22, y + 109, 12, Muted);
            using (var p = new Pen(Line, 1)) g.DrawLine(p, x + 22, y + 143, x + w - 22, y + 143);
            Text(g, a, x + 22, y + 160, 12, White, false, "Consolas");
            Text(g, b, x + 22, y + 187, 12, White, false, "Consolas");
        }

        static void Edge(Graphics g, int x, int y, string id, string title, string body, Color color)
        {
            Box(g, x, y, 555, 135, Panel, Line);
            Text(g, id, x + 20, y + 18, 12, color, false, "Consolas");
            Text(g, title, x + 64, y + 17, 20, White, true);
            Wrap(g, body, new RectangleF(x + 64, y + 55, 455, 62), 14, Muted);
        }

        static byte[] Frame(int sec)
        {
            using (var bitmap = new Bitmap(W, H, PixelFormat.Format24bppRgb))
            using (var graphics = Graphics.FromImage(bitmap))
            using (var ms = new MemoryStream())
            {
                graphics.SmoothingMode = SmoothingMode.AntiAlias;
                graphics.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;
                DrawSlide(graphics, sec);
                bitmap.Save(ms, ImageFormat.Jpeg);
                return ms.ToArray();
            }
        }

        static uint FourCC(string text)
        {
            return BitConverter.ToUInt32(Encoding.ASCII.GetBytes(text), 0);
        }

        static byte[] Chunk(string id, byte[] data)
        {
            using (var ms = new MemoryStream()) using (var bw = new BinaryWriter(ms))
            {
                bw.Write(Encoding.ASCII.GetBytes(id)); bw.Write(data.Length); bw.Write(data);
                if ((data.Length & 1) != 0) bw.Write((byte)0);
                return ms.ToArray();
            }
        }

        static byte[] ListChunk(string type, byte[] payload)
        {
            using (var ms = new MemoryStream()) using (var bw = new BinaryWriter(ms))
            {
                bw.Write(Encoding.ASCII.GetBytes("LIST")); bw.Write(payload.Length + 4);
                bw.Write(Encoding.ASCII.GetBytes(type)); bw.Write(payload);
                if (((payload.Length + 4) & 1) != 0) bw.Write((byte)0);
                return ms.ToArray();
            }
        }

        static byte[] MainHeader(int maxFrame)
        {
            using (var ms = new MemoryStream()) using (var bw = new BinaryWriter(ms))
            {
                bw.Write(1000000u / FPS); bw.Write((uint)(maxFrame * FPS)); bw.Write(0u); bw.Write(0x10u);
                bw.Write((uint)FRAMES); bw.Write(0u); bw.Write(1u); bw.Write((uint)maxFrame);
                bw.Write((uint)W); bw.Write((uint)H); for (int i = 0; i < 4; i++) bw.Write(0u);
                return ms.ToArray();
            }
        }

        static byte[] StreamHeader(int maxFrame)
        {
            using (var ms = new MemoryStream()) using (var bw = new BinaryWriter(ms))
            {
                bw.Write(Encoding.ASCII.GetBytes("vids")); bw.Write(Encoding.ASCII.GetBytes("MJPG"));
                bw.Write(0u); bw.Write((ushort)0); bw.Write((ushort)0); bw.Write(0u);
                bw.Write(1u); bw.Write((uint)FPS); bw.Write(0u); bw.Write((uint)FRAMES);
                bw.Write((uint)maxFrame); bw.Write(0xffffffffu); bw.Write(0u);
                bw.Write((short)0); bw.Write((short)0); bw.Write((short)W); bw.Write((short)H);
                return ms.ToArray();
            }
        }

        static byte[] BitmapHeader(int maxFrame)
        {
            using (var ms = new MemoryStream()) using (var bw = new BinaryWriter(ms))
            {
                bw.Write(40u); bw.Write((int)W); bw.Write((int)H); bw.Write((ushort)1); bw.Write((ushort)24);
                bw.Write(FourCC("MJPG")); bw.Write((uint)maxFrame); bw.Write(0); bw.Write(0); bw.Write(0u); bw.Write(0u);
                return ms.ToArray();
            }
        }

        public static void Make(string outputPath)
        {
            var frames = new List<byte[]>();
            int max = 0;
            for (int i = 0; i < FRAMES; i++) { var frame = Frame(i); frames.Add(frame); if (frame.Length > max) max = frame.Length; }
            var strlBody = Combine(Chunk("strh", StreamHeader(max)), Chunk("strf", BitmapHeader(max)));
            var hdrl = ListChunk("hdrl", Combine(Chunk("avih", MainHeader(max)), ListChunk("strl", strlBody)));
            using (var moviPayload = new MemoryStream()) using (var bw = new BinaryWriter(moviPayload))
            using (var idx = new MemoryStream()) using (var iw = new BinaryWriter(idx))
            {
                bw.Write(Encoding.ASCII.GetBytes("movi"));
                uint offset = 4;
                foreach (var frame in frames)
                {
                    var chunk = Chunk("00dc", frame);
                    bw.Write(chunk);
                    iw.Write(Encoding.ASCII.GetBytes("00dc")); iw.Write(0x10u); iw.Write(offset); iw.Write((uint)frame.Length);
                    offset += (uint)chunk.Length;
                }
                var moviBytes = moviPayload.ToArray();
                using (var file = new FileStream(outputPath, FileMode.Create, FileAccess.Write))
                using (var fw = new BinaryWriter(file))
                {
                    fw.Write(Encoding.ASCII.GetBytes("RIFF"));
                    fw.Write((uint)(4 + hdrl.Length + 8 + moviBytes.Length + 8 + idx.Length));
                    fw.Write(Encoding.ASCII.GetBytes("AVI "));
                    fw.Write(hdrl);
                    fw.Write(Encoding.ASCII.GetBytes("LIST")); fw.Write(moviBytes.Length); fw.Write(moviBytes);
                    fw.Write(Encoding.ASCII.GetBytes("idx1")); fw.Write(idx.Length); fw.Write(idx.ToArray());
                }
            }
        }

        static byte[] Combine(params byte[][] parts)
        {
            using (var ms = new MemoryStream()) { foreach (var part in parts) ms.Write(part, 0, part.Length); return ms.ToArray(); }
        }
    }
}
