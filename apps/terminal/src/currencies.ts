// Sandbox currency catalogs (display + ISO codes). Backend accepts any ISO-4217
// fiat code; execution stays sandbox/testnet. No live rails exist in this build.
export interface FiatCurrency { code: string; nameEn: string; nameBg: string; symbol: string; }
export const FIAT_CURRENCIES: FiatCurrency[] = [
  { code: "EUR", nameEn: "Euro", nameBg: "Евро", symbol: "€" },
  { code: "USD", nameEn: "US Dollar", nameBg: "Щатски долар", symbol: "$" },
  { code: "GBP", nameEn: "British Pound", nameBg: "Британска лира", symbol: "£" },
  { code: "BGN", nameEn: "Bulgarian Lev", nameBg: "Български лев", symbol: "лв" },
  { code: "CHF", nameEn: "Swiss Franc", nameBg: "Швейцарски франк", symbol: "Fr" },
  { code: "SEK", nameEn: "Swedish Krona", nameBg: "Шведска крона", symbol: "kr" },
  { code: "NOK", nameEn: "Norwegian Krone", nameBg: "Норвежка крона", symbol: "kr" },
  { code: "DKK", nameEn: "Danish Krone", nameBg: "Датска крона", symbol: "kr" },
  { code: "PLN", nameEn: "Polish Zloty", nameBg: "Полска злота", symbol: "zł" },
  { code: "CZK", nameEn: "Czech Koruna", nameBg: "Чешка крона", symbol: "Kč" },
  { code: "HUF", nameEn: "Hungarian Forint", nameBg: "Унгарски форинт", symbol: "Ft" },
  { code: "RON", nameEn: "Romanian Leu", nameBg: "Румънска лея", symbol: "lei" },
];

export interface CryptoAsset { id: string; nameEn: string; nameBg: string; network: string; tab: string; }
export const CRYPTO_ASSETS: CryptoAsset[] = [
  { id: "mock:btc:regtest", nameEn: "Bitcoin (regtest)", nameBg: "Биткойн (regtest)", network: "bitcoin-regtest", tab: "crypto" },
  { id: "evm:sepolia", nameEn: "Sepolia ETH (testnet)", nameBg: "Sepolia ETH (testnet)", network: "sepolia-11155111", tab: "evm" },
  { id: "stripe:card", nameEn: "Card via Stripe sandbox", nameBg: "Карта през Stripe sandbox", network: "card", tab: "fiat" },
];
