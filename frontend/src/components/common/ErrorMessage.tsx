export function ErrorMessage({ message }: { message: string }) {
  return <p role="alert" className="error-message">{message}</p>
}
