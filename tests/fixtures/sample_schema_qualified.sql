CREATE TABLE Sales.Customer (
  CustomerID SERIAL PRIMARY KEY,
  Name TEXT NOT NULL
);

CREATE TABLE Sales.SalesOrder (
  OrderID SERIAL PRIMARY KEY,
  CustomerID INT REFERENCES Sales.Customer(CustomerID)
);

ALTER TABLE Sales.SalesOrder ADD CONSTRAINT fk_cust FOREIGN KEY (CustomerID) REFERENCES Sales.Customer(CustomerID);
