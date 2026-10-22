import emmveeLogo from '../../assets/emmvee-logo.png'

// The Emmvee logo is the only brand mark in the app. The PNG is transparent and is
// drawn with no background in both themes. In dark mode a soft white glow and a
// slight brightness lift keep the dark-blue lettering readable without a box.
export default function BrandLogo({ className = 'h-10' }) {
  return <img src={emmveeLogo} alt="Emmvee" className={`w-auto select-none dark:brightness-125 dark:drop-shadow-[0_0_6px_rgba(255,255,255,0.45)] ${className}`} draggable="false" />
}
