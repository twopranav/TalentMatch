import { isStaffRole } from '../../utils/profileForm'
import Field from '../ui/Field'

// Controlled field group for UserProfileUpdate. `idPrefix` keeps label/input ids
// unique when the group is rendered inside a modal on a page that has another copy.
export default function ProfileFields({ role, form, onChange, idPrefix = 'profile' }) {
  const set = (field) => (e) => onChange((f) => ({ ...f, [field]: e.target.value }))
  const field = (name, label, extra = {}) => (
    <Field id={`${idPrefix}-${name}`} label={label} value={form[name]} onChange={set(name)} {...extra} />
  )
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">{field('full_name', 'Full name')}{field('phone', 'Phone', { type: 'tel' })}</div>
      {isStaffRole(role) ? (
        <div className="grid grid-cols-2 gap-4">{field('company', 'Company')}{field('title', 'Title')}</div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4">
            {field('location', 'Location')}
            {field('experience_years', 'Years of experience', { type: 'number', min: '0' })}
          </div>
          {field('desired_role', 'Desired role')}
          {field('skills', 'Skills', { placeholder: 'React, SQL, Python', hint: 'Separate skills with commas.' })}
        </>
      )}
    </div>
  )
}
