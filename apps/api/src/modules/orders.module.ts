import { Module } from "@nestjs/common";
import { OrdersController, DevicesController } from "../orders.controller";

@Module({ controllers: [OrdersController, DevicesController] })
export class OrdersModule {}
