# UniqVoice Design System

This file captures the source-of-truth design tokens and patterns derived from the `/create` page. All other pages must align with these standards to ensure a premium, cohesive user experience.

## 1. Global Header (Navigation)
- **Removal**: The multi-step "Voice Angle Create" stepper and the top-right user profile icon (`account_circle`) have been removed from the header globally.
- **Structure**: The header should only contain the "UniqVoice" logo aligned to the left and centered vertically.
- **Specs**: 
  - Height: `h-20`
  - Background: `bg-surface`
  - Border: Bottom border `border-b border-border-subtle`
  - Container padding: `px-margin-mobile md:px-margin-desktop`

## 2. Typography System
All pages must use the exact font families and sizes defined in the unified Tailwind config.

### Font Families
- **Headlines**: `Source Serif 4` (for `headline-lg`, `headline-md`, `headline-lg-mobile`)
- **Body & Labels**: `Inter` (for `body-lg`, `body-md`, `label-caps`)
- **Data/Logs**: `JetBrains Mono` (for `data-mono`)

### Type Scale
- `headline-lg`: 40px / 48px line-height, bold (700)
- `headline-lg-mobile`: 32px / 38px line-height, bold (700)
- `headline-md`: 24px / 32px line-height, semi-bold (600)
- `body-lg`: 18px / 28px line-height, regular (400)
- `body-md`: 16px / 24px line-height, regular (400)
- `data-mono`: 14px / 20px line-height, regular (400)
- `label-caps`: 12px / 16px line-height, letter-spacing 0.05em, semi-bold (600)

## 3. Color Palette
The color tokens must match the `/create` page exactly. The old harsh black/white theme has been replaced with the premium editorial theme.

### Primary Tokens
- `primary`: `#4113d9` (Deep violet)
- `magic-violet`: `#5A3DF0` (Vibrant violet accent)
- `secondary`: `#006c45` (Forest green for success/completion states)
- `surface`: `#FBFAF6` (Warm off-white for cards and nav)
- `canvas`: `#F3F1EA` (Page background)
- `ink-primary`: `#17171B` (Soft black for main text)
- `ink-secondary`: `#4A4A52` (Muted text)
- `border-subtle`: `#E5E5E5`
- `border-hairline`: `#E2DED3`

## 4. Spacing & Containers
- **Max Width**: `max-w-container-max` (`1280px`)
- **Desktop Padding**: `px-margin-desktop` (`40px`)
- **Mobile Padding**: `px-margin-mobile` (`20px`)
- **Gaps**: Standard component gap is `component-gap` (`16px`); larger layout gaps use `gutter` (`24px`).

## 5. Components
### Cards & Panels
- **Standard Card**: `bg-surface border border-border-hairline rounded-xl shadow-sm`
- **Inner Containers**: Use `bg-surface-container` or `bg-surface-container/30` for nested depth.

### Buttons
- **Primary Button**: `bg-primary text-white font-label-caps rounded-xl px-8 py-3 shadow-lg hover:translate-y-[-2px] transition-all`
- **Secondary/Action Button**: `bg-surface border border-border-hairline text-ink-secondary hover:bg-surface-container transition-colors rounded-xl px-5 h-12 flex items-center justify-center font-label-caps`
