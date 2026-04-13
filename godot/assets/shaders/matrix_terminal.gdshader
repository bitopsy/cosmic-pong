shader_type spatial;
render_mode unshaded, cull_disabled, blend_add;

// Cosmic Matrix Terminal Shader
// Creates the green-on-black glowing panel effect for VR displays

uniform sampler2D screen_texture : hint_screen_texture, filter_linear_mipmap;
uniform float scan_speed : hint_range(0.1, 5.0) = 1.2;
uniform float scan_intensity : hint_range(0.0, 0.5) = 0.08;
uniform float glow_strength : hint_range(0.0, 2.0) = 0.4;
uniform float flicker_rate : hint_range(0.0, 10.0) = 2.5;
uniform float flicker_amount : hint_range(0.0, 0.1) = 0.015;
uniform vec4 tint_color : source_color = vec4(0.0, 1.0, 0.25, 1.0);
uniform float pixel_scale : hint_range(1.0, 4.0) = 1.5;
uniform float vignette_strength : hint_range(0.0, 1.0) = 0.35;
uniform float chromatic_aberration : hint_range(0.0, 0.01) = 0.002;
uniform bool enable_crt_curve = true;
uniform float crt_curvature : hint_range(0.0, 0.3) = 0.08;

varying vec2 v_uv;

void vertex() {
    v_uv = UV;
}

// CRT barrel distortion
vec2 crt_distort(vec2 uv, float k) {
    vec2 centered = uv * 2.0 - 1.0;
    float r2 = dot(centered, centered);
    vec2 distorted = centered * (1.0 + k * r2);
    return distorted * 0.5 + 0.5;
}

// Scanline contribution
float scanline(vec2 uv, float time) {
    float y_scroll  = fract(uv.y * 180.0 + time * scan_speed);
    float scan      = smoothstep(0.0, 0.3, y_scroll) * smoothstep(1.0, 0.7, y_scroll);
    return 1.0 - scan * scan_intensity;
}

// Phosphor glow approximation
vec3 phosphor_glow(vec3 col, vec2 uv) {
    float dist = length(uv - 0.5);
    return col * (1.0 + glow_strength * exp(-dist * 6.0));
}

// Vignette
float vignette(vec2 uv) {
    uv = uv * 2.0 - 1.0;
    return 1.0 - dot(uv, uv) * vignette_strength;
}

// Subtle flicker
float flicker(float time) {
    float f1 = sin(time * flicker_rate * 17.3) * 0.5 + 0.5;
    float f2 = sin(time * flicker_rate * 31.7) * 0.5 + 0.5;
    return 1.0 - flicker_amount * (f1 * f2);
}

void fragment() {
    float time = TIME;
    vec2 uv    = v_uv;

    // CRT curve
    if (enable_crt_curve) {
        uv = crt_distort(uv, crt_curvature);
        if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
            ALBEDO = vec3(0.0);
            ALPHA  = 1.0;
            return;
        }
    }

    // Pixel grid (CRT dot mask approximation)
    vec2 pix = floor(uv / vec2(pixel_scale / 1024.0));
    vec2 pix_uv = pix * vec2(pixel_scale / 1024.0) + vec2(pixel_scale / 2048.0);

    // Chromatic aberration (separate R/G/B channels slightly)
    float r_chan = texture(screen_texture, pix_uv + vec2(chromatic_aberration, 0.0)).r;
    float g_chan = texture(screen_texture, pix_uv).g;
    float b_chan = texture(screen_texture, pix_uv - vec2(chromatic_aberration, 0.0)).b;
    vec3 col = vec3(r_chan, g_chan, b_chan);

    // Tint to matrix green
    col = col * tint_color.rgb;

    // Scanlines
    col *= scanline(uv, time);

    // Phosphor glow
    col = phosphor_glow(col, uv);

    // Vignette
    col *= vignette(uv);

    // Flicker
    col *= flicker(time);

    // Edge border glow
    vec2 edge  = abs(uv * 2.0 - 1.0);
    float border = 1.0 - smoothstep(0.92, 1.0, max(edge.x, edge.y));
    col += tint_color.rgb * 0.08 * (1.0 - border);

    ALBEDO = col;
    ALPHA  = 0.95;
    EMISSION = col * 0.3;
}
