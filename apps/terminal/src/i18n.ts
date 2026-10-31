export const dict = {
  en: {
    newOrder: "New order", amount: "Amount (EUR)", create: "Create & show QR",
    scan: "Customer scans this QR to review the exact agreement version, fees and quote, then authorizes.",
    receipt: "Technical receipt (NOT a fiscal receipt)", merchant: "Merchant", beneficiary: "Beneficiary",
  },
  bg: {
    newOrder: "Нова поръчка", amount: "Сума (EUR)", create: "Създай и покажи QR",
    scan: "Клиентът сканира QR кода, за да прегледа точната версия на споразумението, таксите и офертата, след което оторизира.",
    receipt: "Техническа бележка (НЕ е фискален бон)", merchant: "Търговец", beneficiary: "Получател",
  },
} as const;
export type Locale = keyof typeof dict;
