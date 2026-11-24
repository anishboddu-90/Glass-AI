using System;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Animation;

namespace GlassSidebar
{
    // Tiny animation toolkit: fades, rises, pops, staggers — all with Apple-ish easing.
    internal static class Animate
    {
        public static readonly IEasingFunction Out = new CubicEase { EasingMode = EasingMode.EaseOut };
        public static readonly IEasingFunction Spring = new BackEase { EasingMode = EasingMode.EaseOut, Amplitude = 0.45 };
        public static readonly IEasingFunction Smooth = new SineEase { EasingMode = EasingMode.EaseInOut };

        static Duration Ms(double ms) { return new Duration(TimeSpan.FromMilliseconds(ms)); }

        public static void Fade(UIElement el, double to, double ms, double delay = 0, Action done = null)
        {
            var a = new DoubleAnimation(to, Ms(ms)) { EasingFunction = Out, BeginTime = TimeSpan.FromMilliseconds(delay) };
            if (done != null) a.Completed += delegate { done(); };
            el.BeginAnimation(UIElement.OpacityProperty, a);
        }

        // fade + rise from below (messages, cards)
        public static void Rise(FrameworkElement el, double delay = 0, double distance = 12)
        {
            var shift = new TranslateTransform(0, distance);
            el.RenderTransform = shift;
            el.Opacity = 0;
            el.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(0, 1, Ms(260)) { EasingFunction = Out, BeginTime = TimeSpan.FromMilliseconds(delay) });
            shift.BeginAnimation(TranslateTransform.YProperty, new DoubleAnimation(distance, 0, Ms(420)) { EasingFunction = Spring, BeginTime = TimeSpan.FromMilliseconds(delay) });
        }

        // scale in from slightly small (chips, menus, toasts)
        public static void Pop(FrameworkElement el, double delay = 0, double from = 0.85)
        {
            var st = el.RenderTransform as ScaleTransform;
            if (st == null || st.IsFrozen) { st = new ScaleTransform(1, 1); el.RenderTransform = st; }
            if (el.RenderTransformOrigin == new Point(0, 0)) el.RenderTransformOrigin = new Point(0.5, 0.5);
            el.Opacity = 0;
            var b = TimeSpan.FromMilliseconds(delay);
            el.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(0, 1, Ms(180)) { EasingFunction = Out, BeginTime = b });
            st.BeginAnimation(ScaleTransform.ScaleXProperty, new DoubleAnimation(from, 1, Ms(380)) { EasingFunction = Spring, BeginTime = b });
            st.BeginAnimation(ScaleTransform.ScaleYProperty, new DoubleAnimation(from, 1, Ms(380)) { EasingFunction = Spring, BeginTime = b });
        }

        // scale + fade out, then collapse
        public static void PopOut(FrameworkElement el, Action done)
        {
            var st = el.RenderTransform as ScaleTransform;
            if (st == null || st.IsFrozen) { st = new ScaleTransform(1, 1); el.RenderTransform = st; }
            el.RenderTransformOrigin = new Point(0.5, 0.5);
            var fade = new DoubleAnimation(0, Ms(140)) { EasingFunction = Out };
            fade.Completed += delegate { if (done != null) done(); };
            el.BeginAnimation(UIElement.OpacityProperty, fade);
            st.BeginAnimation(ScaleTransform.ScaleXProperty, new DoubleAnimation(0.8, Ms(140)));
            st.BeginAnimation(ScaleTransform.ScaleYProperty, new DoubleAnimation(0.8, Ms(140)));
        }

        // slide horizontally in (panes, settings)
        public static void SlideIn(FrameworkElement el, double fromX, double ms = 360)
        {
            var tt = el.RenderTransform as TranslateTransform;
            if (tt == null || tt.IsFrozen) { tt = new TranslateTransform(); el.RenderTransform = tt; }
            el.Opacity = 0;
            el.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(0, 1, Ms(ms * 0.7)) { EasingFunction = Out });
            tt.BeginAnimation(TranslateTransform.XProperty, new DoubleAnimation(fromX, 0, Ms(ms)) { EasingFunction = Spring });
        }

        // endless gentle pulse (opacity), e.g. "thinking" shimmer
        public static void Breathe(UIElement el, double lo, double hi, double ms)
        {
            el.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(lo, hi, Ms(ms))
            { AutoReverse = true, RepeatBehavior = RepeatBehavior.Forever, EasingFunction = Smooth });
        }

        public static void Stop(UIElement el) { el.BeginAnimation(UIElement.OpacityProperty, null); }

        // animate a brush's colour (selection highlights etc.)
        public static void ColorTo(SolidColorBrush b, System.Windows.Media.Color to, double ms = 200)
        {
            if (b.IsFrozen) return;
            b.BeginAnimation(SolidColorBrush.ColorProperty, new ColorAnimation(to, Ms(ms)) { EasingFunction = Out });
        }
    }
}
