type AuthLayoutProps = {
  children: React.ReactNode
}

export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className='container grid h-svh max-w-none items-center justify-center'>
      <div className='mx-auto flex w-full flex-col justify-center space-y-2 py-8 sm:p-8'>
        <div className='mb-6 flex flex-col items-center justify-center gap-3'>
          <img
            src='/images/aria-logo.png'
            alt='ARIA logo'
            className='h-20 w-20 object-contain'
          />
          <div className='flex flex-col items-center gap-1'>
            <h1 className='text-2xl font-extrabold tracking-widest text-slate-950 uppercase dark:text-white'>
              ARIA
            </h1>
            <p className='font-mono text-[0.6rem] font-semibold tracking-[0.28em] text-orange-500 uppercase dark:text-orange-400'>
              Intelligence Platform
            </p>
          </div>
        </div>
        {children}
      </div>
    </div>
  )
}
