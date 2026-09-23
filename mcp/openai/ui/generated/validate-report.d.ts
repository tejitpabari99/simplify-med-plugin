type ValidationError = { instancePath?: string; message?: string };
type Validator = ((data: unknown) => boolean) & { errors?: ValidationError[] | null };
declare const validate: Validator;
export default validate;
