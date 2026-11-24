using System;
using System.IO;
using System.Linq;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using Forms = System.Windows.Forms;
using Drawing = System.Drawing;

namespace GlassSidebar
{
    // Turns files, clipboard images and screenshots into message attachments.
    internal static class Attachments
    {
        const int MaxImageSide = 1600;          // big images are shrunk to keep requests fast
        const long MaxPdfBytes = 30L * 1024 * 1024;
        const long MaxTextBytes = 400 * 1024;

        static readonly string[] ImageExt = { ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff" };
        static readonly string[] TextExt = {
            ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".log", ".env",
            ".html", ".htm", ".css", ".scss", ".js", ".jsx", ".ts", ".tsx", ".py", ".rb", ".go", ".rs", ".java", ".kt",
            ".c", ".h", ".cpp", ".hpp", ".cs", ".swift", ".m", ".php", ".sh", ".bat", ".ps1", ".sql", ".lua", ".r", ".dart",
            ".vue", ".svelte", ".gradle", ".cfg", ".conf", ".tex" };

        public const string FileFilter =
            "Images, PDFs, text & code|*.png;*.jpg;*.jpeg;*.gif;*.bmp;*.webp;*.pdf;*.txt;*.md;*.csv;*.json;*.xml;*.yaml;*.yml;*.html;*.css;*.js;*.ts;*.tsx;*.py;*.cs;*.java;*.c;*.cpp;*.go;*.rs;*.swift;*.sql;*.sh;*.log|All files|*.*";

        public static Attachment FromFile(string path)
        {
            var fi = new FileInfo(path);
            string ext = fi.Extension.ToLowerInvariant();
            if (ImageExt.Contains(ext))
            {
                using (var fs = File.OpenRead(path))
                {
                    var dec = BitmapDecoder.Create(fs, BitmapCreateOptions.PreservePixelFormat, BitmapCacheOption.OnLoad);
                    return FromBitmap(dec.Frames[0], fi.Name);
                }
            }
            if (ext == ".pdf")
            {
                if (fi.Length > MaxPdfBytes) throw new Exception(fi.Name + " is larger than 30 MB.");
                return new Attachment { Name = fi.Name, Kind = "pdf", MediaType = "application/pdf", Data = Convert.ToBase64String(File.ReadAllBytes(path)), Bytes = fi.Length };
            }
            if (TextExt.Contains(ext) || LooksLikeText(path))
            {
                if (fi.Length > MaxTextBytes) throw new Exception(fi.Name + " is too large to send as text (max 400 KB).");
                return new Attachment { Name = fi.Name, Kind = "text", MediaType = "text/plain", Text = File.ReadAllText(path), Bytes = fi.Length };
            }
            throw new Exception("Can't attach " + fi.Name + " — use images, PDFs, or text/code files.");
        }

        static bool LooksLikeText(string path)
        {
            try
            {
                var buf = new byte[4096];
                int n;
                using (var fs = File.OpenRead(path)) n = fs.Read(buf, 0, buf.Length);
                for (int i = 0; i < n; i++) if (buf[i] == 0) return false;
                return n > 0;
            }
            catch { return false; }
        }

        // Re-encodes any bitmap as JPEG (or PNG if it has transparency), shrinking it if huge.
        public static Attachment FromBitmap(BitmapSource src, string name)
        {
            BitmapSource bmp = src;
            int longSide = Math.Max(bmp.PixelWidth, bmp.PixelHeight);
            if (longSide > MaxImageSide)
            {
                double k = (double)MaxImageSide / longSide;
                bmp = new TransformedBitmap(bmp, new ScaleTransform(k, k));
            }
            bool alpha = bmp.Format == PixelFormats.Bgra32 || bmp.Format == PixelFormats.Pbgra32;
            BitmapEncoder enc;
            if (alpha && name.EndsWith(".png", StringComparison.OrdinalIgnoreCase)) enc = new PngBitmapEncoder();
            else
            {
                if (bmp.Format != PixelFormats.Bgr24 && bmp.Format != PixelFormats.Bgr32)
                    bmp = new FormatConvertedBitmap(bmp, PixelFormats.Bgr24, null, 0);
                enc = new JpegBitmapEncoder { QualityLevel = 88 };
            }
            enc.Frames.Add(BitmapFrame.Create(bmp));
            using (var ms = new MemoryStream())
            {
                enc.Save(ms);
                bool png = enc is PngBitmapEncoder;
                return new Attachment
                {
                    Name = name, Kind = "image", MediaType = png ? "image/png" : "image/jpeg",
                    Data = Convert.ToBase64String(ms.ToArray()), Bytes = ms.Length
                };
            }
        }

        public static Attachment FromClipboard()
        {
            if (!Clipboard.ContainsImage()) return null;
            var img = Clipboard.GetImage();
            return img == null ? null : FromBitmap(img, "Pasted image.jpg"); // clipboard alpha is unreliable: flatten to JPEG
        }

        // Screenshot of the monitor the panel is on. Our window is excluded from capture,
        // so the shot shows exactly what's *behind* the sidebar.
        public static Attachment CaptureScreen(Forms.Screen screen)
        {
            var b = screen.Bounds;
            using (var bmp = new Drawing.Bitmap(b.Width, b.Height, Drawing.Imaging.PixelFormat.Format24bppRgb))
            {
                using (var g = Drawing.Graphics.FromImage(bmp))
                    g.CopyFromScreen(b.Left, b.Top, 0, 0, b.Size, Drawing.CopyPixelOperation.SourceCopy);
                using (var ms = new MemoryStream())
                {
                    bmp.Save(ms, Drawing.Imaging.ImageFormat.Png);
                    ms.Position = 0;
                    var dec = BitmapDecoder.Create(ms, BitmapCreateOptions.None, BitmapCacheOption.OnLoad);
                    return FromBitmap(dec.Frames[0], "Screen " + DateTime.Now.ToString("HH:mm") + ".jpg");
                }
            }
        }

        public static BitmapImage Thumbnail(Attachment a, int px)
        {
            if (a.Kind != "image" || string.IsNullOrEmpty(a.Data)) return null;
            try
            {
                var img = new BitmapImage();
                img.BeginInit();
                img.StreamSource = new MemoryStream(Convert.FromBase64String(a.Data));
                img.DecodePixelWidth = px;
                img.CacheOption = BitmapCacheOption.OnLoad;
                img.EndInit();
                img.Freeze();
                return img;
            }
            catch { return null; }
        }

        public static string SizeText(long bytes)
        {
            if (bytes < 1024) return bytes + " B";
            if (bytes < 1024 * 1024) return (bytes / 1024) + " KB";
            return (bytes / (1024.0 * 1024.0)).ToString("0.0") + " MB";
        }
    }
}
